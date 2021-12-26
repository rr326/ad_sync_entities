import json
from dataclasses import dataclass
from typing import Any, Callable, Optional

import adplus
from appdaemon.adapi import ADAPI

adplus.importlib.reload(adplus)

# pylint: disable=unused-argument


@dataclass
class EventPattern:
    pattern_fromhost: Optional[str] = None
    pattern_tohost: Optional[str] = None
    pattern_event_type: Optional[str] = None
    pattern_entity: Optional[str] = None


class EventParts:
    """
    Splits a topic string into its components.
    If does not match, it will NOT fail. Just reports self.matches == False

    event:
        mqtt_shared/<fromhost>/<tohost>/<event_type>/<entity>
        mqtt_shared/haven/seattle/state/light.outside_porch
        mqtt_shared/haven/all/state/light.outside_porch

        mqtt_shared/haven/*/ping

    match_host, match_event_type, match_entity:
        None = match any value (like regex ".*")
        !str = must NOT equal string (eg: pattern_host="!pihaven" means host != "pihaven")
        str = must equal string
        TODO (maybe) - more powerful matching
    """

    def __init__(
        self,
        adapi: ADAPI,
        mqtt_base_topic: str,
        event: str,
        pattern: Optional[EventPattern],
    ):
        self.adapi = adapi
        self.mqtt_base_topic = mqtt_base_topic
        self.event = event
        self._pattern_fromhost = pattern.pattern_fromhost if pattern else None
        self._pattern_tohost = pattern.pattern_tohost if pattern else None
        self._pattern_event_type = pattern.pattern_event_type if pattern else None
        self._pattern_entity = pattern.pattern_entity if pattern else None

        self.matches = False
        self.fromhost = None
        self.tohost = None
        self.event_type = None
        self.entity = None

        split_ok = self._do_split()
        if split_ok:
            self.matches = self._do_match()

    def _do_split(self):
        parts = self.event.split("/")
        if len(parts) < 4 or len(parts) > 5:
            self.adapi.log(f"match failed - improper format: {self.event}")
            return False

        if parts[0] != self.mqtt_base_topic:
            self.adapi.log(
                f"split failed - does not start with {self.mqtt_base_topic}: {self.event}"
            )
            return False

        self.fromhost = parts[1]
        self.tohost = parts[2]
        self.event_type = parts[3]
        self.entity = parts[4] if len(parts) >= 5 else None
        return True

    def _match_pattern(
        self, value: Optional[str], pattern: Optional[str], special_all: bool = False
    ) -> bool:
        """
        None --> True
        !pattern != value --> True
        pattern == value --> True
        Otherwise False

        if "special_all",
        pattern=="all" --> True
        """
        if pattern is None:
            return True 
        if special_all:
            if pattern == "all":
                return True
            if value == "all":
                return True
        if pattern[0] == "!":
            return pattern[1:] != value
        else:
            return pattern == value

    def _do_match(self):
        return (
            self._match_pattern(self.fromhost, self._pattern_fromhost, special_all=True)
            and self._match_pattern(self.tohost, self._pattern_tohost, special_all=True)
            and self._match_pattern(self.event_type, self._pattern_event_type)
            and self._match_pattern(self.entity, self._pattern_entity)
        )


# Dispatcher Callback Signature
# my_callback(fromhost, tohost, event_str, entity_str, payload, payload_asobj=None) -> Any
DispatcherCallbackType = Callable[
    [str, str, str, Optional[str], Optional[str], Optional[object]], Optional[Any]
]


@dataclass
class EventListener:
    name: str
    pattern: EventPattern
    callback: Optional[DispatcherCallbackType]


class EventListenerDispatcher:
    """
    This will dispatch *ALREADY CAUGHT* mqtt events and send them to the proper callback.

    Usage:

    dispatcher = EventListenerDispatcher(self.adapi)
    def my_callback(fromhost, tohost, event_str, entity_str, payload, payload_asobj=None) -> Any: pass

    dispatcher.add_listener("listen for all state changes", EventPattern(event_type="state"), my_callback)

    # new event from MQ caught: "mqtt_shared/pi-haven/state/light.outside_porch 'on'"
    dispatcher.dispatch(mq_event, payload)
    """

    def __init__(self, adapi: ADAPI, mqtt_base_topic: str):
        self.adapi = adapi
        self.mqtt_base_topic = mqtt_base_topic

        self._listeners = {}

    def add_listener(
        self, name, pattern: EventPattern, callback: Optional[DispatcherCallbackType]
    ):
        if name in self._listeners:
            self.adapi.log(
                f"add_listener - being asked to re-register following listener: {name}",
                LEVEL="WARNING",
            )
            del self._listeners["name"]

        self._listeners[name] = EventListener(
            name, pattern, callback if callback else self.default_callback
        )

    def remove_listener(self, name):
        if name not in self._listeners:
            self.adapi.log(
                f"remove_listener - being asked to remove listener that is not found: {name}",
                LEVEL="WARNING",
            )
            return
        del self._listeners["name"]

    def default_callback(
        self, fromhost, tohost, event_type, entity, payload, payload_as_obj
    ) -> list:
        return [
            self.adapi.log(
                f"default_callback: {fromhost}/{tohost}/{event_type}/{entity} -- {payload}"
            )
        ]

    def safe_payload_as_obj(self, payload) -> Optional[object]:
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None
        except Exception:
            self.adapi.log(f"Unexpected error trying to json decode: {payload}")
            return None

    def dispatch(self, mq_event, payload) -> list:
        did_dispatch = False
        results = []
        for name, listener in self._listeners.items():
            ep = EventParts(
                self.adapi, self.mqtt_base_topic, mq_event, listener.pattern
            )
            if ep.matches:
                # self.adapi.log(f"dispatcher: dispatching to: {name}")
                results.append(
                    listener.callback(
                        ep.fromhost,
                        ep.tohost,
                        ep.event_type,
                        ep.entity,
                        payload,
                        self.safe_payload_as_obj(payload),
                    )
                )
                did_dispatch = True

        if not did_dispatch:
            self.adapi.log(f"dispatcher: could not find pattern to match: {mq_event}.")
        return results
