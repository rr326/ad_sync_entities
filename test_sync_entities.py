import adplus

adplus.importlib.reload(adplus)

# pylint: disable=unused-argument,use-implicit-booleaness-not-comparison

from _sync_entities.dispatcher import EventListenerDispatcher, EventParts, EventPattern

MQTT_DEFAULT_BASE_TOPIC = "mqtt_shared"


class TestSyncEntitiesViaMqtt(adplus.Hass):
    """
    This runs some tests that would normally be run under pytest.
    But getting it all working with pytest is more trouble than it is worth.
    (Since Appdaeomon loads modules dynamically.)
    """

    def initialize(self):
        self.log("Initialize")

        self.run_in(self.test_event_parts, 0)
        self.run_in(self.test_dispatcher, 0)

    def test_event_parts(self, _):
        adapi = self.get_ad_api()

        # mqtt_shared
        topic = "BOGUS/haven/seattle/ping"
        assert not EventParts(adapi, "mqtt_shared", topic, None).matches

        topic = f"mqtt_shared/haven/seattle/ping"
        assert EventParts(adapi, "mqtt_shared", topic, None).matches

        # all, *, //
        topic = f"mqtt_shared/haven/seattle/ping"
        assert EventParts(adapi, "mqtt_shared", topic, EventPattern(pattern_tohost="seattle")).matches

        topic = f"mqtt_shared/haven/seattle/ping"
        assert EventParts(adapi, "mqtt_shared", topic, EventPattern(pattern_tohost="all")).matches

        topic = f"mqtt_shared/haven/seattle/ping"
        assert EventParts(adapi, "mqtt_shared", topic, EventPattern(pattern_tohost="*")).matches

        topic = f"mqtt_shared/haven/seattle/ping"
        assert EventParts(adapi, "mqtt_shared", topic, EventPattern(pattern_tohost=None)).matches

        topic = f"mqtt_shared/haven/BOGUS/ping"
        assert not EventParts(adapi, "mqtt_shared", topic, EventPattern(pattern_tohost="seattle")).matches

        # topic too long
        topic = f"mqtt_shared/haven/seattle/state/myentity/BOGUS"
        assert not EventParts(adapi, "mqtt_shared", topic, None).matches

        # topic with entity
        topic = f"mqtt_shared/haven/seattle/state/myentity"
        assert EventParts(adapi, "mqtt_shared", topic, None).matches

        # from haven
        topic = f"mqtt_shared/haven/seattle/state/myentity"
        assert EventParts(adapi, "mqtt_shared", topic, EventPattern(pattern_fromhost="haven")).matches

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
            EventPattern("haven",  "seattle", "state", "myentity"),
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
        dispatcher.add_listener("listener1", event_pattern1, callback
        )
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
