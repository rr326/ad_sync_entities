from appdaemon.adapi import ADAPI
from appdaemon.plugins.mqtt import mqttapi as mqtt

from _sync_entities.sync_plugin import Plugin
from _sync_entities.sync_dispatcher import EventPattern

# pylint: disable=unused-argument


class PluginPingPong(Plugin):
    def initialize(self):
        self.dispatcher.add_listener(
            "ping/pong",
            EventPattern(
                pattern_fromhost=f"!{self.myhostname}", 
                pattern_tohost=f"{self.myhostname}",
                pattern_event_type="ping",
            ),
            self.ping_callback,
        )

    def ping_callback(
        self, fromhost, tohost, event, entity, payload, payload_asobj=None
    ):
        self.adapi.log(
            f"PING/PONG - {self.mqtt_base_topic}/{fromhost}/{tohost}/pong - {payload} [myhostname: {self.myhostname}]"
        )
        self.mqtt.mqtt_publish(
            topic=f"{self.mqtt_base_topic}/{self.myhostname}/{fromhost}/pong",
            payload=payload,
            namespace="mqtt",
        )
