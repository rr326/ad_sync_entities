from _sync_entities.sync_dispatcher import EventListenerDispatcher
from appdaemon.adapi import ADAPI
from appdaemon.plugins.mqtt.mqttapi import Mqtt as mqttapi


class Plugin:
    def __init__(
        self,
        adapi: ADAPI,
        mqtt: mqttapi,
        dispatcher: EventListenerDispatcher,
        mqtt_base_topic: str,
        argsn: dict,
        myhostname: str,
    ):
        self.adapi = adapi
        self.mqtt = mqtt
        self.dispatcher = dispatcher
        self.mqtt_base_topic = mqtt_base_topic
        self.argsn = argsn
        self.myhostname = myhostname

        self.initialize()

        self.adapi.log(f"Plugin Initialized: {self.__class__.__name__}", level="DEBUG")

    def initialize(self):
        raise NotImplementedError("Overide in inherited object")
