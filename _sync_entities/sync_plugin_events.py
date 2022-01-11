import json
from typing import Optional

from _sync_entities.sync_dispatcher import EventPattern
from _sync_entities.sync_plugin import Plugin
from _sync_entities.sync_utils import entity_local_to_remote
from appdaemon.adapi import ADAPI
from appdaemon.plugins.hass.hassplugin import HassPlugin

# pylint: disable=unused-argument


class PluginEvents(Plugin):
    def initialize(self):
        self.adapi.run_in(
            self.register_inbound_event, 0
        )  # EG: mqtt_shared/haven/seattle/event/light.office off
        self.adapi.run_in(
            self.register_outbound_service, 0
        )  # EG: call_service("default", "sync_entities_via_mqtt", "set_state", {"entity_id":"sensor.light_office_pihaven","value":"on"})
        self.adapi.run_in(
            self.register_outbound_event, 0
        )  # EG: dashboard: fire-event(app.sync_entities_via_mqtt, action, payload)
        # self.adapi.run_in(self.test_event_mechanism, 0.1)

    def register_inbound_event(self, kwargs):
        def callback_inbound_event(
            fromhost, tohost, event, entity, payload, payload_asobj=None
        ):
            """
            Act on an event received from a remote host:

                mqtt_shared/haven/seattle/event/light.office off

            event == "event"
            payload == desired state

            """
            self.adapi.log(
                f"EVENT - received: {fromhost}/{tohost}/{event}/{entity} data: {payload}",
                level="DEBUG",
            )
            if not self.adapi.entity_exists(entity):
                self.adapi.log(
                    f"callback_inbound_event(): entity does not exist: {entity}.",
                    level="WARNING",
                )
                return
            if event != "event":
                self.adapi.log(
                    f"callback_inbound_event(): [NOT IMPLEMENTED] - got unexpected event: {event}",
                    level="WARNING",
                )
                return
            try:
                _ = json.loads(payload)
            except json.JSONDecodeError:
                pass
            else:
                self.adapi.log(
                    f"callback_inbound_event(): [NOT IMPLEMENTED] - got JSON payload. Currently only accept simple states: |{payload}|",
                    level="WARNING",
                )
                return

            # Do it
            _inbound_take_hass_action(
                self.adapi,
                self.mqtt.get_plugin_api("HASS"),
                event,
                entity,
                payload,
                payload_asobj,
            )

        self.dispatcher.add_listener(
            "event_in",
            EventPattern(
                pattern_fromhost=f"!{self.myhostname}",
                pattern_tohost=f"{self.myhostname}",
                pattern_event_type="event",
            ),
            callback_inbound_event,
        )

    def register_outbound_service(self, kwargs):
        """
        Register a service for signaling to a remote entity that it should change the state of an object.

        Note - this will NOT work from Hass / Dashboard directly! This only works within Appdaemon.

        Use events (see register_events) to signal from Hass / Dashboard.

        call_service("default", "sync_entities_via_mqtt", "set_state", {"entity_id":"sensor.light_office_pihaven","state":"on"})
        call_service("default", "sync_entities_via_mqtt", "toggle_state", {"entity_id":"sensor.light_office_pihaven"})

        What it does:
            mqtt_publish("mqtt_shared/pihaven/state", payload="on")
        """

        def callback_outbound_service(
            namespace: str, service: str, action: str, kwargs
        ) -> None:
            self.adapi.log(
                f"sync_service_callback(namespace={namespace}, service={service}, action={action}, kwargs={kwargs})",
                level="DEBUG",
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

            (remote_entity, remote_host) = entity_local_to_remote(local_entity)
            if remote_host is None:
                raise RuntimeError(
                    f"Programming error - invalid remote_entity_id: {local_entity}"
                )

            if action == "set_state":
                value = kwargs["state"]
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

        hass = self.mqtt.get_plugin_api("HASS")

        hass.register_service(
            "sync_entities_via_mqtt/set_state", callback_outbound_service
        )
        hass.register_service(
            "sync_entities_via_mqtt/toggle_state", callback_outbound_service
        )
        self.adapi.log(
            "register_service: sync_entities_via_mqtt -- set_state, toggle_state",
            level="DEBUG",
        )

    def register_outbound_event(self, kwargs):
        """
        To signal this plugin to tell a remote entity to change state,
        you need to go through this rigamorole:

        scripts.yaml
            fire_event_sync_entities_via_mqtt_toggle:
            alias: "Fire Event - sync_entities_via_mqtt_toggle"
            sequence:
            - event: app.sync_entities_via_mqtt
                event_data:
                    action: toggle_state
                    entity_id: "{{ data.entity_id }}"

        dashboard.yaml
          - type: "custom:button-card"
            entity: light.office
            name: Test sync_entities_via_mqtt_toggle
            show_state: true
            tap_action:
                action: call-service
                service: script.fire_event_sync_entities_via_mqtt_toggle
                service_data:
                  entity_id: light.office_seattle
        """

        def callback_outbound_event(event, data, kwargs):
            self.adapi.log(
                f"callback_outbound_event(): {event} -- {data} -- {kwargs}",
                level="DEBUG",
            )
            self.adapi.call_service(
                f'sync_entities_via_mqtt/{data.get("action", "NO_ACTION")}',
                entity_id=data.get("entity_id"),
                state=data.get("state"),
            )

        self.adapi.listen_event(
            callback_outbound_event, event="app.sync_entities_via_mqtt"
        )
        self.adapi.log("Registered event: app.sync_entities_via_mqtt", level="DEBUG")

    def test_event_mechanism(self, _):
        self.adapi.log("TEST event mechanism")
        if self.myhostname == "haven":
            self.adapi.log("Calling: sync_entities_via_mqtt/toggle_state")
            self.adapi.call_service(
                "sync_entities_via_mqtt/toggle_state", entity_id="light.office_seattle"
            )  # pyright: reportGeneralTypeIssues=false


def _inbound_take_hass_action(
    adapi: ADAPI,
    hass: HassPlugin,
    event: str,
    entity: str,
    payload: str,
    payload_asobj: Optional[dict] = None,
):
    """
    Given and entity, and a state, take an appropriate action.

    EG:
    "light.office", "on" --> hass.turn_on("light.office")
    "input_select.home_mode", "Away" --> hass.select_option("input_select.home_mode", "Away")


    Dev Notes:

    * Unfortunately, you can NOT simply set the state on an entity.
    * If you do that, it WILL set the state, but it will NOT change the underlying Hass device.
    """
    platform, sep, _ = entity.partition(".")
    if not sep:
        adapi.log(
            f"_inbound_take_hass_action(): entity of improper format: {entity}",
            level="WARNING",
        )
        return

    if platform in ["light", "switch", "scene", "script"]:
        if payload == "on":
            hass.turn_on(entity_id=entity)
        elif payload == "off":
            hass.turn_off(entity_id=entity)
        else:
            adapi.log(
                f"_inbound_take_hass_action(): unexpected state for entity: {entity} -- {payload}",
                level="WARNING",
            )
    elif platform == "input_number":
        hass.set_value(entity, payload)
    elif platform == "input_text":
        hass.set_textvalue(entity, payload)
    elif platform == "input_select":
        hass.select_option(entity, payload)
    else:
        adapi.log(
            f"_inbound_take_hass_action(): NOT IMPLEMENTED: Unexpected platform for entity: {entity}",
            level="WARNING",
        )
        return

    if adapi.get_state(entity_id=entity) != payload:
        adapi.log(
            f"event_in_callback(): Not able to set state correctly.", level="WARNING"
        )
