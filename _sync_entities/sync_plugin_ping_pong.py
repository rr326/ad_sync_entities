import datetime as dt
from typing import Callable, Optional, Dict, Tuple

from _sync_entities.sync_dispatcher import EventPattern
from _sync_entities.sync_plugin import Plugin
from appdaemon.plugins.hass.hassplugin import HassPlugin

# pylint: disable=unused-argument


class PluginPingPong(Plugin):
    def initialize(self):
        self.pong_callbacks: Dict[str, Callable] = {}

        self.dispatcher.add_listener(
            "ping",
            EventPattern(
                pattern_fromhost=f"!{self.myhostname}",
                pattern_tohost=f"{self.myhostname}",
                pattern_event_type="ping",
            ),
            self.cb_ping,
        )

        self.dispatcher.add_listener(
            "pong",
            EventPattern(
                pattern_fromhost=f"!{self.myhostname}",
                pattern_tohost=f"{self.myhostname}",
                pattern_event_type="pong",
            ),
            self.cb_pong,
        )

        self.adapi.run_in(self.register_ping_service, 0)

        # Testing
        # self.adapi.run_in(self.test_ping_pong_service, 0)

    def cb_ping(self, fromhost, tohost, event, entity, payload, payload_asobj=None):
        self.adapi.log(
            f"PING - {self.mqtt_base_topic}/{fromhost}/{tohost}/pong - {payload} [myhostname: {self.myhostname}]",
            level="DEBUG",
        )
        self.mqtt.mqtt_publish(
            topic=f"{self.mqtt_base_topic}/{self.myhostname}/{fromhost}/pong",
            payload=payload,
            namespace="mqtt",
        )

    def cb_pong(self, fromhost, tohost, event, entity, payload, payload_asobj=None):
        self.adapi.log(
            f"PONG - {self.mqtt_base_topic}/{fromhost}/{tohost}/pong - {payload}",
            level="DEBUG",
        )
        key = f"{fromhost}--{payload}"
        if key in self.pong_callbacks:
            self.adapi.log(f"pong_callback found", level="DEBUG")
            self.pong_callbacks[key]()  # success_cb
            del self.pong_callbacks[key]
        else:
            pass  # already timed out

    def register_ping_service(self, kwargs):
        """
        Register a service that allows you to call ping/pong

        Note - this will NOT work from Hass / Dashboard directly! This only works within Appdaemon.

        self.adapi.call_service(
            "sync_entities_via_mqtt/ping",
            tohost="haven",
            timeout=20,  # Seconds
            success_cb=cb_success, # fn
            timeout_cb=cb_timeout, # fn
        )

        What it does:
            mqtt_publish("mqtt_shared/seattle/haven/ping", payload="<timestamp>")
            
            Then calls cb_success() or cb_timeout() if timeout.
        """

        def callback_ping_service(
            namespace: str, service: str, action: str, kwargs
        ) -> None:
            self.adapi.log(
                f"callback_ping_service(namespace={namespace}, service={service}, action={action}, kwargs={kwargs})",
                level="DEBUG",
            )

            # Check args
            tohost = kwargs.get("tohost")
            if not tohost:
                raise RuntimeError(
                    f"Invalid parameters - no 'tohost': callback_ping_service(namespace={namespace}, service={service}, action={action}, kwargs={kwargs})"
                )
            timeout = kwargs.get("timeout")
            success_cb = kwargs.get("success_cb")
            timeout_cb = kwargs.get("timeout_cb")

            if (timeout or success_cb or timeout_cb) and not (
                timeout is not None and success_cb and timeout_cb
            ):
                raise RuntimeError(
                    f"Invalid parameters - need all or none of timeout, success_cb, timeout_cb: callback_ping_service(namespace={namespace}, service={service}, action={action}, kwargs={kwargs})"
                )

            #
            # Do it
            #

            # Send PING
            payload = dt.datetime.now().isoformat()
            self.mqtt.mqtt_publish(
                topic=f"{self.mqtt_base_topic}/{self.myhostname}/{tohost}/ping",
                payload=payload,
                namespace="mqtt",
            )

            # Optional: Wait for Pong
            if timeout is not None:
                key = f"{tohost}--{payload}"
                if key in self.pong_callbacks:
                    raise RuntimeError(
                        f"pong callback key collision. Programming error?"
                    )
                self.pong_callbacks[key] = success_cb

                def run_timout(kwargs):
                    self.adapi.log(f"PONG TIMEOUT - {key}", level="DEBUG")
                    if key in self.pong_callbacks:
                        timeout_cb()
                        del self.pong_callbacks[key]
                    else:
                        pass  # already run since it didn't timeout

                self.adapi.run_in(run_timout, timeout)

        hass = self.mqtt.get_plugin_api("HASS")

        hass.register_service("sync_entities_via_mqtt/ping", callback_ping_service)

        self.adapi.log(
            "register_service: sync_entities_via_mqtt -- ping",
            level="DEBUG",
        )

    def test_ping_pong_service(self, kwargs):
        self.adapi.log(f"##test_ping_pong_service(): Test Ping/Pong Service")

        def cb_success():
            self.adapi.log(f"##test_ping_pong_service(): ** PONG - SUCCESS")

        def cb_timeout():
            self.adapi.log(f"##test_ping_pong_service(): ** PONG - TIMEOUT")

        self.adapi.call_service(
            "sync_entities_via_mqtt/ping",
            tohost="haven",
            timeout=0,  # Will succeed (if remote is slow or has an intentional sleep)
            success_cb=cb_success,
            timeout_cb=cb_timeout,
        )

        self.adapi.call_service(
            "sync_entities_via_mqtt/ping",
            tohost="haven",
            timeout=3,  # Should timeout
            success_cb=cb_success,
            timeout_cb=cb_timeout,
        )
