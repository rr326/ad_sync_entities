from appdaemon.plugins.mqtt import mqttapi as mqtt

# pylint: disable=unused-argument,use-implicit-booleaness-not-comparison

from _sync_entities.sync_dispatcher import (
    EventListenerDispatcher,
    EventParts,
    EventPattern,
)

MQTT_DEFAULT_BASE_TOPIC = "mqtt_shared"


class TestSyncEntitiesViaMqtt(mqtt.Mqtt):
    """
    This runs some tests that would normally be run under pytest.
    But getting it all working with pytest is more trouble than it is worth.
    (Since Appdaeomon loads modules dynamically.)
    """

    def initialize(self):
        self.log("Initialize")
        self.adapi = self.get_ad_api()

        self.run_in(self.test_event_parts, 0)
        self.run_in(self.test_dispatcher, 0.1)
        self.run_in(self.test_plugin_ping_pong, 0.2)

    def test_event_parts(self, _):
        adapi = self.get_ad_api()

        # mqtt_shared
        topic = "BOGUS/haven/seattle/ping"
        assert not EventParts(adapi, "mqtt_shared", topic, None).matches

        topic = f"mqtt_shared/haven/seattle/ping"
        assert EventParts(adapi, "mqtt_shared", topic, None).matches

        # all,  //
        topic = f"mqtt_shared/haven/seattle/ping"
        assert EventParts(
            adapi, "mqtt_shared", topic, EventPattern(pattern_tohost="seattle")
        ).matches

        topic = f"mqtt_shared/haven/seattle/ping"
        assert EventParts(
            adapi, "mqtt_shared", topic, EventPattern(pattern_tohost="all")
        ).matches

        topic = f"mqtt_shared/haven/seattle/ping"
        assert EventParts(
            adapi, "mqtt_shared", topic, EventPattern(pattern_tohost=None)
        ).matches

        topic = f"mqtt_shared/haven/BOGUS/ping"
        assert not EventParts(
            adapi, "mqtt_shared", topic, EventPattern(pattern_tohost="seattle")
        ).matches

        topic = f"mqtt_shared/haven/seattle/ping"
        assert not EventParts(
            adapi,
            "mqtt_shared",
            topic,
            EventPattern(pattern_fromhost="!haven", pattern_tohost="seattle"),
        ).matches

        # topic too long
        topic = f"mqtt_shared/haven/seattle/state/myentity/BOGUS"
        assert not EventParts(adapi, "mqtt_shared", topic, None).matches

        # topic with entity
        topic = f"mqtt_shared/haven/seattle/state/myentity"
        assert EventParts(adapi, "mqtt_shared", topic, None).matches

        # from haven
        topic = f"mqtt_shared/haven/seattle/state/myentity"
        assert EventParts(
            adapi, "mqtt_shared", topic, EventPattern(pattern_fromhost="haven")
        ).matches

        topic = f"mqtt_shared/BOGUS/state/myentity"
        assert not EventParts(
            adapi, "mqtt_shared", topic, EventPattern("haven")
        ).matches

        # type=state
        topic = f"mqtt_shared/haven/seattle/state/myentity"
        assert EventParts(
            adapi, "mqtt_shared", topic, EventPattern(pattern_event_type="state")
        ).matches

        topic = f"mqtt_shared/haven/seattle/BOGUS/myentity"
        assert not EventParts(
            adapi, "mqtt_shared", topic, EventPattern(pattern_event_type="state")
        ).matches

        # entity=myentity
        topic = f"mqtt_shared/haven/seattle/state/myentity"
        assert EventParts(
            adapi, "mqtt_shared", topic, EventPattern(pattern_entity="myentity")
        ).matches

        topic = f"mqtt_shared/haven/seattle/state/BOGUS"
        assert not EventParts(
            adapi, "mqtt_shared", topic, EventPattern(pattern_entity="myentity")
        ).matches

        # from "haven", from "!haven"
        topic = f"mqtt_shared/haven/seattle/state/entity"
        assert EventParts(
            adapi, "mqtt_shared", topic, EventPattern(pattern_fromhost="haven")
        ).matches

        topic = f"mqtt_shared/seattle/haven/state/entity"
        assert not EventParts(
            adapi, "mqtt_shared", topic, EventPattern(pattern_fromhost="haven")
        ).matches

        topic = f"mqtt_shared/haven/seattle/state/entity"
        assert not EventParts(
            adapi, "mqtt_shared", topic, EventPattern(pattern_fromhost="!haven")
        ).matches

        topic = f"mqtt_shared/seattle/haven/state/entity"
        assert EventParts(
            adapi, "mqtt_shared", topic, EventPattern(pattern_fromhost="!haven")
        ).matches

        # Fully qualified
        topic = f"mqtt_shared/haven/seattle/state/myentity"
        assert EventParts(
            adapi,
            "mqtt_shared",
            topic,
            EventPattern("haven", "seattle", "state", "myentity"),
        ).matches

        self.log("**test_event_parts() - all pass!**")

    def test_dispatcher(self, _):
        adapi = self.get_ad_api()

        def callback(fromhost, tohost, event_type, entity, payload, payload_as_obj):
            return payload

        dispatcher = EventListenerDispatcher(adapi, "mqtt_shared")

        assert (
            dispatcher.dispatch("mqtt_shared/haven/seattle/state/myentity", "1") == []
        )  # no registered callbacks

        event_pattern1 = EventPattern("haven", "all", "state", "myentity")
        dispatcher.add_listener("listener1", event_pattern1, callback)
        assert dispatcher.dispatch("mqtt_shared/haven/seattle/state/myentity", "1") == [
            "1"
        ]
        assert dispatcher.dispatch("mqtt_shared/haven/seattle/state/BOGUS", "1") == []

        event_pattern2 = EventPattern("haven", "all", "state", None)
        dispatcher.add_listener("listener2", event_pattern2, callback)
        assert dispatcher.dispatch("mqtt_shared/haven/seattle/state/myentity", "1") == [
            "1",
            "1",
        ]
        assert dispatcher.dispatch(
            "mqtt_shared/haven/seattle/state/DIFFERENT", "1"
        ) == ["1"]

        self.log("**test_dispatcher() - all pass!**")

    """
    Testing plugins

    Too hard to build infrastructure to proplery test these.
    Instead, just print to the logs and eyeball results. 

    (Otherwise have to asynchrounously capture MQTT stream and
    asynchronously assert)

    It is best if you turn off any other server's sync_entities
    so you aren't dealing with their responses!
    """

    def tp(self, topic, message, expectation):
        """
        tp - test_plugin
        """
        self.log(f"TEST:   {topic} -- {message}")
        self.log(f'EXPECT: {expectation if expectation else "NO RESPONSE"}')

        self.mqtt_publish(
            topic=topic,
            payload=message,
            namespace="mqtt",
        )

    def test_plugin_ping_pong(self, _):
        self.log("*** TEST PING/PONG ***")

        self.tp(
            "mqtt_shared/seattle/haven/ping",
            "test-ping",
            "mqtt_shared/haven/seattle/pong -- test-ping",
        )

        self.tp(
            "mqtt_shared/seattle/all/ping",
            "test-ping",
            "mqtt_shared/haven/seattle/pong -- test-ping",
        )

        self.tp("mqtt_shared/seattle/haven/pong", "test-ping", None)
        self.tp("mqtt_shared/haven/haven/ping", "test-ping", None)
        self.tp("mqtt_shared/haven/all/ping", "test-ping", None)
        self.tp("mqtt_shared/all/haven/ping", "test-ping", None)

        self.log("*** end: TEST PING/PONG ***")
