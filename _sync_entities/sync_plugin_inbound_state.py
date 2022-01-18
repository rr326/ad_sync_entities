from _sync_entities.sync_dispatcher import EventPattern
from _sync_entities.sync_plugin import Plugin
from _sync_entities.sync_utils import entity_local_to_remote, entity_remote_to_local

# pylint: disable=unused-argument


class PluginInboundState(Plugin):
    def initialize(self):
        self.state_entities = self.argsn.get("state_for_entities", [])

        if not self.state_entities:
            self.adapi.log(
                f"PluginInboundState - no entities in config to watch for. argsn: {self.argsn}",
                level="WARNING",
            )

        self.dispatcher.add_listener(
            "inbound_state",
            EventPattern(
                pattern_fromhost=f"!{self.myhostname}",
                pattern_tohost=self.myhostname,
                pattern_event_type="state",
            ),
            self.inbound_state_callback,
        )

        self.adapi.run_in(self.register_state_entities, 0)

    def inbound_state_callback(
        self, fromhost, tohost, event, entity, payload, payload_asobj=None
    ):
        self.adapi.log(f"inbound_state_callback entity: {entity}", level="DEBUG")
        try:
            # Make sure I'm not doing something wrong and getting a remote entity like _xxSeattlexx
            (_, _) = entity_local_to_remote(entity)
        except ValueError:
            pass
        else:
            # Should not be here - programming error
            self.adapi.log(
                f"inbound_state_callback(): Ignoring /{fromhost}/{tohost}/{event}/{entity} -- {payload}",
                level="ERROR",
            )
            return

        self.adapi.log(
            f"inbound_state_callback(): set_state: /{fromhost}/{tohost}/{event}/{entity} -- {payload}",
            level="DEBUG",
        )

        remote_entity = entity_remote_to_local(entity, fromhost)
        self.adapi.log(
            f"inbound_callback() set_state({remote_entity}, state={payload})",
            level="DEBUG",
        )
        self.adapi.set_state(f"{remote_entity}", state=payload, namespace="default")

    def register_state_entities(self, kwargs):
        def state_callback(entity, attribute, old, new, kwargs):
            self.adapi.log(
                f"state_callback(): {entity} -- {attribute} -- {new}", level="DEBUG"
            )
            self.mqtt.mqtt_publish(
                topic=f"{self.mqtt_base_topic}/{self.myhostname}/all/state/{entity}",
                payload=new,
                namespace="mqtt",
            )

        for entity in self.state_entities:
            cur_state = self.adapi.get_state(entity)
            self.adapi.log(f"** registered {entity} -- {cur_state}", level="DEBUG")
            self.adapi.listen_state(state_callback, entity, immediate=True)
