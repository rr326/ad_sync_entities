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

        import _sync_entities.sync_plugin_ping_pong
        import _sync_entities.sync_plugin_print_all

        reload(_sync_entities.sync_plugin_ping_pong)
        reload(_sync_entities.sync_plugin_print_all)

        self._plugins = [_sync_entities.sync_plugin_print_all.PluginPrintAll, _sync_entities.sync_plugin_ping_pong.PluginPingPong]
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

        # Register event dispatch listeners - processing INCOMING messages
        # self.dispatcher.add_listener("print all", EventPattern(), None)

        # self.dispatcher.add_listener(
        #     "inbound state",
        #     EventPattern(
        #         pattern_fromhost=f"!{self.myhostname}",  # Only listen to for events I didn't create
        #         pattern_event_type="state",
        #     ),
        #     self.inbound_state_callback,
        # )

        # # Register OUTGOING messages
        # self.run_in(self.register_state_entities, 0)

        # # Register sync_servic
        # self.run_in(self.register_sync_service, 0)

        # def test_sync_service(kwargs):
        #     self.log("***test_sync_service()***")
        #     self.call_service(
        #         "sync_entities_via_mqtt/toggle_state",
        #         entity_id="light.office_seattle",
        #         namespace="default",
        #     )

        # self.run_in(test_sync_service, 1)

        # Listen to all MQ events
        self.listen_event(
            self.mq_listener,
            "MQTT_MESSAGE",
            wildcard=f"{self.mqtt_base_topic}/#",
            namespace="mqtt",
        )

    """
    Entity naming / renaming.

    # Constraints
    * You need a remote entity to have a HOSTNAME suffix
    * The suffix can only be alphanumeric characters. Symbols won't work.
    * EXCEPT - you CAN have underscore (_) 
        * BUT can't end with it
        * You can not have two in a row
    * You can only create *sensor* entities. (Actually, you can create
      any entity, but they are read only. So sensors are more sensible.)

    # Rules
    host: seattle, entity: light.office -> sensor.light_office_seattle
    """

    def entity_add_hostname(self, entity: str, host: str) -> str:
        """
        light.named_light, host -> light.named_light_host

        opposite: entity_split_hostname()
        """

        # Note- you can't use any symbols for the host delimiter. I tried many.
        # 500 error
        return f"{entity}_{host}"

    def entity_split_hostname(self, entity: str) -> Tuple[str, Optional[str]]:
        """
        light.named_light_pihaven -> ("light.named_light", "pihaven")
        light.local_light -> ("light.local_light", None)

        opposite: entity_add_myhostname()
        """
        match = re.fullmatch(r"(.*)_([^#]+)", entity)
        if match:
            return (match.group(1), match.group(2))
        else:
            return (entity, None)

    def mq_listener(self, event, data, kwargs):
        self.log(f"mq_listener: {event}, {data}")
        self.dispatcher.dispatch(data.get("topic"), data.get("payload"))

    def inbound_state_callback(
        self, fromhost, tohost, event, entity, payload, payload_asobj=None
    ):
        (_, entity_host) = self.entity_split_hostname(entity)
        if entity_host is not None:
            # Should not be here - programming error
            self.log(
                f"inbound_state_callback(): Ignoring /{fromhost}/{tohost}/{event}/{entity} -- {payload}",
                level="ERROR",
            )
            return

        self.log(
            f"inbound_state_callback(): set_state: /{fromhost}/{tohost}/{event}/{entity} -- {payload}"
        )

        remote_entity = self.entity_add_hostname(entity, fromhost)
        self.log(f"inbound_callback() set_state({remote_entity}, state={payload})")
        self.set_state(f"{remote_entity}", state=payload, namespace="default")

    def register_state_entities(self, kwargs):
        def state_callback(entity, attribute, old, new, kwargs):
            self.log(f"state_callback(): {entity} -- {attribute} -- {new}")
            self.mqtt_publish(
                topic=f"{self.mqtt_base_topic}/{self.myhostname}/state/{entity}",
                payload=new,
                namespace="mqtt",
            )

        for entity in self.state_entities:
            cur_state = self.get_state(entity)
            self.log(f"** registered {entity} -- {cur_state}")
            self._state_listeners.add(self.listen_state(state_callback, entity))

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
