from appdaemon.adapi import ADAPI
from appdaemon.plugins.mqtt import mqttapi as mqtt

from _sync_entities.sync_plugin import Plugin
from _sync_entities.sync_dispatcher import EventPattern
from _sync_entities.sync_utils import entity_add_hostname, entity_split_hostname

# pylint: disable=unused-argument


class PluginEvents(Plugin):
    def initialize(self):
        self.dispatcher.add_listener(
            "event_in",
            EventPattern(
                pattern_fromhost=f"!{self.myhostname}",
                pattern_tohost=f"{self.myhostname}",
                pattern_event_type="event",
            ),
            self.event_in_callback,
        )

        self.adapi.run_in(self.register_sync_service, 0)

        self.adapi.run_in(self.test_event_mechanism, 0.1)

    def event_in_callback(
        self, fromhost, tohost, event, entity, payload, payload_asobj=None
    ):
        self.adapi.log(
            f"EVENT - received: {fromhost}/{tohost}/{event}/{entity} data: {payload}"
        )
        if not self.adapi.entity_exists(entity):
            self.adapi.log(f"event_in_callback(): entity does not exist: {entity}.")
            return
        if payload not in ["on", "off"]:
            self.adapi.log(f"event_in_callback(): [NOT IMPLEMENTED] - payload not in 'on', 'off'. Got: {payload}")
            return

        # Super annoying - self.adapi.set_state() does not work! It should.         
        hass = self.mqtt.get_plugin_api("HASS")
        if payload == "on":
            hass.turn_on(entity_id=entity)
        elif payload == "off":
            hass.turn_off(entity_id=entity)
        else:
            self.adapi.log(f'NOT IMPLEMENTED - only turn_on and turn_off. desired state: {payload}', level="WARNING")
            
        if self.adapi.get_state(entity_id=entity) != payload:
            self.adapi.log(f'event_in_callback(): Not able to set state correctly.')


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
            self.adapi.log(
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

            (remote_entity, remote_host) = entity_split_hostname(local_entity)
            if remote_host is None:
                raise RuntimeError(
                    f"Programming error - invalid remote_entity_id: {local_entity}"
                )

            if action == "set_state":
                value = kwargs["value"]
            elif action == "toggle_state":
                if not self.adapi.entity_exists(local_entity):
                    raise RuntimeError(f"entity does not exist: {local_entity}")
                cur_state = self.adapi.get_state(entity_id=local_entity)
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

            self.mqtt.mqtt_publish(
                topic=f"{self.mqtt_base_topic}/{self.myhostname}/{remote_host}/event/{remote_entity}",
                payload=value,
                namespace="mqtt",
            )

        self.adapi.register_service(
            "sync_entities_via_mqtt/change_state", sync_service_callback
        )
        self.adapi.register_service(
            "sync_entities_via_mqtt/toggle_state", sync_service_callback
        )
        self.adapi.log(
            "register_service: sync_entities_via_mqtt -- change_state, toggle_state"
        )

    def test_event_mechanism(self, _):
        self.adapi.log("TEST event mechanism")
        if self.myhostname == "haven":
            self.adapi.log("Calling: sync_entities_via_mqtt/toggle_state")
            self.adapi.call_service(
                "sync_entities_via_mqtt/toggle_state", entity_id="light.office_seattle"
            )  # pyright: reportGeneralTypeIssues=false
