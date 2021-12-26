from appdaemon.adapi import ADAPI
from appdaemon.plugins.mqtt import mqttapi as mqtt

from _sync_entities.sync_plugin import Plugin
from _sync_entities.sync_dispatcher import EventPattern

# pylint: disable=unused-argument


class PluginPrintAll(Plugin):
    def initialize(self):
        self.dispatcher.add_listener(
            "print_all",
            EventPattern(),
            None, # Uses default callback
        )

