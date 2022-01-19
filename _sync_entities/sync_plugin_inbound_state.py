from typing import Callable, Optional
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

        self.adapi.run_in(
            self.register_inbound_send_state_event, 0
        )  # EG: mqtt_shared/seattle/all/send_state

        # Ask other sites to send me their state, upon startup
        self.adapi.run_in(self.ask_remotes_for_state, 1)

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

    def __register_or_send_state(
        self, tohost: str, action_fn: Callable[[Callable, str], None]
    ):
        # Does two jobs - registering a listener on state, or sending state
        def state_callback(entity, _, __, cur_state, ___):
            self.adapi.log(f"state_callback(): {entity}  -- {cur_state}", level="INFO")
            self.mqtt.mqtt_publish(
                topic=f"{self.mqtt_base_topic}/{self.myhostname}/{tohost}/state/{entity}",
                payload=cur_state,
                namespace="mqtt",
            )

        for entity in self.state_entities:
            action_fn(state_callback, entity)

    def register_state_entities(self, kwargs):
        def do_listen_state(state_callback: Callable, entity: str):
            self.adapi.log(f"** registered state_listener for: {entity}", level="DEBUG")
            self.adapi.listen_state(state_callback, entity, immediate=True)

        self.__register_or_send_state("all", do_listen_state)

    def send_state_entities_tohost(self, tohost):
        def do_send_state(state_callback: Callable, entity: str):
            cur_state = self.adapi.get_state(entity)
            state_callback(entity, None, None, cur_state, None)

        self.__register_or_send_state(tohost, do_send_state)

    def register_inbound_send_state_event(self, kwargs):
        def callback_inbound_send_state(
            fromhost, tohost, event, entity, payload, payload_asobj=None
        ):
            """
            Act on an event received from a remote host:
                mqtt_shared/seattle/all/send_state
            """
            self.adapi.log(
                f"EVENT - received: {fromhost}/{tohost}/{event}/{entity} data: {payload}",
                level="INFO",
            )
            self.send_state_entities_tohost(fromhost)

        self.dispatcher.add_listener(
            "event_send_state",
            EventPattern(
                pattern_fromhost=f"!{self.myhostname}",
                pattern_tohost=f"{self.myhostname}",
                pattern_event_type="send_state",
            ),
            callback_inbound_send_state,
        )

    def ask_remotes_for_state(self, kwargs):
        self.mqtt.mqtt_publish(
            topic=f"{self.mqtt_base_topic}/{self.myhostname}/all/send_state",
            namespace="mqtt",
        )
