from _sync_entities.sync_dispatcher import EventPattern
from _sync_entities.sync_plugin import Plugin

# pylint: disable=unused-argument


class PluginPrintAll(Plugin):
    def initialize(self):
        self.dispatcher.add_listener(
            "print_all",
            EventPattern(),
            None,  # Uses default callback
        )
