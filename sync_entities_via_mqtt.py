import re
from typing import Optional, Tuple, List

import adplus
from appdaemon.plugins.mqtt import mqttapi as mqtt
from importlib import reload


from _sync_entities.sync_dispatcher import EventListenerDispatcher, EventPattern
from _sync_entities.sync_plugin import Plugin

# pylint: disable=unused-argument


class SyncEntitiesViaMqtt(mqtt.Mqtt):
    """
    This syncs the state of selected entities across multiple HA installations via MQTT.

    It requires both HA installations to share state via MQTT (probably via a bridge)
    with a shared topic (eg: mqtt_shared)

    Devnotes
    * If you create a new entity with set_state(entity_id="something_new"),
    it will *create* the entity, but it will not function normally.
    For instance, you can't use the UI to turn the entity off. You can't
    even listen on a "call_service" event, since it won't trigger.
    (Despite what it says here: https://community.home-assistant.io/t/dynamically-create-ha-entity/66869)
    * Instead, create a read-only sensor.
    * Then to trigger a change, in the UI override "tap-action" to have it fire off an MQTT message
    to tell the source machine to turn it change state, which will then reflect back locally.
    """

    MQTT_DEFAULT_BASE_TOPIC = "mqtt_shared"

    SCHEMA = {
        "myhostname": {
            "required": True,
            "type": "string",
            "regex": "^[^-]+$",  # No dashes permitted
        },
        "mqtt_base_topic": {
            "required": False,
            "type": "string",
            "default": MQTT_DEFAULT_BASE_TOPIC,
        },
        "state_for_entities": {
            "required": False,
            "type": "list",
            "schema": {"type": "string"},
        },
    }

    def initialize(self):
        self.log("Initialize")
        self.adapi = self.get_ad_api()
        self.argsn = adplus.normalized_args(self, self.SCHEMA, self.args, debug=False)
        self.state_entities = self.argsn.get("state_for_entities")
        self._state_listeners = set()
        self.myhostname = self.argsn.get("myhostname", "HOSTNAME_NOT_SET")
        self.mqtt_base_topic = self.argsn.get(
            "mqtt_base_topic", self.MQTT_DEFAULT_BASE_TOPIC
        )
        self.dispatcher = EventListenerDispatcher(
            self.get_ad_api(), self.mqtt_base_topic
        )

        # Required for auto-reloading during development.
        # Also see "global_dependencies" and "global-modules" in .yaml
        # pylint: disable=import-outside-toplevel
        import _sync_entities.sync_plugin_ping_pong
        import _sync_entities.sync_plugin_print_all
        import _sync_entities.sync_plugin_inbound_state

        reload(_sync_entities.sync_plugin_ping_pong)
        reload(_sync_entities.sync_plugin_print_all)
        reload(_sync_entities.sync_plugin_inbound_state)

        self._plugins = [
            _sync_entities.sync_plugin_print_all.PluginPrintAll,
            _sync_entities.sync_plugin_ping_pong.PluginPingPong,
            _sync_entities.sync_plugin_inbound_state.PluginInboundState,
        ]

        self._plugin_handles: List[Plugin] = []
        for plugin in self._plugins:
            self._plugin_handles.append(
                plugin(
                    self.adapi,
                    self,
                    self.dispatcher,
                    self.mqtt_base_topic,
                    self.argsn,
                    self.myhostname,
                )
            )

        # Note - this will not work if you have previously registered wildcard="#"
        self.mqtt_unsubscribe(
            "#", namespace="mqtt"
        )  # Be safe, though this will hurt other apps. Figure out.
        self.mqtt_subscribe(f"{self.mqtt_base_topic}/#", namespace="mqtt")

        # Dispatch to all mqtt_base_topic events
        self.listen_event(
            self.mq_listener,
            "MQTT_MESSAGE",
            wildcard=f"{self.mqtt_base_topic}/#",
            namespace="mqtt",
        )

    def mq_listener(self, event, data, kwargs):
        self.log(f"mq_listener: {event}, {data}")
        self.dispatcher.dispatch(data.get("topic"), data.get("payload"))

    def register_sync_service(self, kwargs):
        """
        Register a service for signaling to a remote entity that it should change the state of an object

        call_service("default", "sync_entities_via_mqtt", "set_state", {"entity_id":"sensor.light_office_pihaven","value":"on"})
        call_service("default", "sync_entities_via_mqtt", "toggle_state", {"entity_id":"sensor.light_office_pihaven"})

        What it does:
            mqtt_publish("mqtt_shared/pihaven/state", payload="on")
        """

        def sync_service_callback(
            namespace: str, service: str, action: str, kwargs
        ) -> None:
            self.log(
                f"sync_service_callback(namespace={namespace}, service={service}, action={action}, kwargs={kwargs})"
            )

            if (
                namespace != "default"
                or action not in ["set_state", "toggle_state"]
                or "entity_id" not in kwargs
            ):
                raise RuntimeError(
                    f"Invalid parameters: sync_service_callback(namespace={namespace}, service={service}, action={action}, kwargs={kwargs})"
                )

            local_entity = kwargs["entity_id"]

            (remote_entity, remote_host) = self.entity_split_hostname(local_entity)
            if remote_host is None:
                raise RuntimeError(
                    f"Programming error - invalid remote_entity_id: {local_entity}"
                )

            if action == "set_state":
                value = kwargs["value"]
            elif action == "toggle_state":
                if not self.entity_exists(local_entity):
                    raise RuntimeError(f"entity does not exist: {local_entity}")
                cur_state = self.get_state(entity_id=local_entity)
                if cur_state == "on":
                    value = "off"
                elif cur_state == "off":
                    value = "on"
                else:
                    raise RuntimeError(
                        f"Unexpected state value for {local_entity}: {cur_state}"
                    )
            else:
                raise RuntimeError(f"Invalid action: |{action}|, type: {type(action)}")

            self.mqtt_publish(
                topic=f"{self.mqtt_base_topic}/{self.myhostname}/{remote_host}/state/{remote_entity}",
                payload=value,
                namespace="mqtt",
            )

        self.register_service(
            "sync_entities_via_mqtt/change_state", sync_service_callback
        )
        self.register_service(
            "sync_entities_via_mqtt/toggle_state", sync_service_callback
        )
        self.log(
            "register_service: sync_entities_via_mqtt -- change_state, toggle_state"
        )
