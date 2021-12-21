import adplus

adplus.importlib.reload(adplus)

# pylint: disable=unused-argument

from .dispatcher import EventListenerDispatcher, EventParts, EventPattern

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
        mqtt_base_topic = MQTT_DEFAULT_BASE_TOPIC

        topic = "BOGUS/pi-haven/ping"
        assert EventParts(adapi, mqtt_base_topic, topic, None).matches is False

        topic = f"{mqtt_base_topic}/pi-haven/ping"
        assert EventParts(adapi, mqtt_base_topic, topic, None).matches is True

        topic = f"{mqtt_base_topic}/pi-haven/state/myentity/BOGUS"
        assert EventParts(adapi, mqtt_base_topic, topic, None).matches is False

        topic = f"{mqtt_base_topic}/pi-haven/state/myentity"
        assert EventParts(adapi, mqtt_base_topic, topic, None).matches is True

        topic = f"{mqtt_base_topic}/pi-haven/state/myentity"
        assert (
            EventParts(adapi, mqtt_base_topic, topic, EventPattern("pi-haven")).matches
            is True
        )

        topic = f"{mqtt_base_topic}/BOGUS/state/myentity"
        assert (
            EventParts(adapi, mqtt_base_topic, topic, EventPattern("pi-haven")).matches
            is False
        )

        topic = f"{mqtt_base_topic}/pi-haven/state/myentity"
        assert (
            EventParts(
                adapi, mqtt_base_topic, topic, EventPattern(pattern_event_type="state")
            ).matches
            is True
        )

        topic = f"{mqtt_base_topic}/pi-haven/BOGUS/myentity"
        assert (
            EventParts(
                adapi, mqtt_base_topic, topic, EventPattern(pattern_event_type="state")
            ).matches
            is False
        )

        topic = f"{mqtt_base_topic}/pi-haven/state/myentity"
        assert (
            EventParts(
                adapi, mqtt_base_topic, topic, EventPattern(pattern_entity="myentity")
            ).matches
            is True
        )

        topic = f"{mqtt_base_topic}/pi-haven/state/BOGUS"
        assert (
            EventParts(
                adapi, mqtt_base_topic, topic, EventPattern(pattern_entity="myentity")
            ).matches
            is False
        )

        topic = f"{mqtt_base_topic}/pi-haven/state/entity"
        assert (
            EventParts(
                adapi, mqtt_base_topic, topic, EventPattern(pattern_host="pi-haven")
            ).matches
            is True
        )

        topic = f"{mqtt_base_topic}/pi-seattle/state/entity"
        assert (
            EventParts(
                adapi, mqtt_base_topic, topic, EventPattern(pattern_host="pi-haven")
            ).matches
            is False
        )

        topic = f"{mqtt_base_topic}/pi-haven/state/entity"
        assert (
            EventParts(
                adapi, mqtt_base_topic, topic, EventPattern(pattern_host="!pi-haven")
            ).matches
            is False
        )

        topic = f"{mqtt_base_topic}/pi-seattle/state/entity"
        assert (
            EventParts(
                adapi, mqtt_base_topic, topic, EventPattern(pattern_host="!pi-haven")
            ).matches
            is True
        )

        topic = f"{mqtt_base_topic}/pi-haven/state/myentity"
        assert (
            EventParts(
                adapi,
                mqtt_base_topic,
                topic,
                EventPattern("pi-haven", "state", "myentity"),
            ).matches
            is True
        )

        self.log("**test_event_parts() - all pass!**")

    def test_dispatcher(self, _):
        adapi = self.get_ad_api()
        mqtt_base_topic = MQTT_DEFAULT_BASE_TOPIC

        def callback(host, event_type, entity, payload, payload_as_obj):
            return payload

        dispatcher = EventListenerDispatcher(adapi, mqtt_base_topic)

        assert (
            dispatcher.dispatch("mqtt_shared/pi-haven/state/myentity", "1") == []
        )  # no registered callbacks

        event_pattern1 = EventPattern("pi-haven", "state", "myentity")
        dispatcher.add_listener("/pi-haven/state/myentity", event_pattern1, callback)
        assert dispatcher.dispatch("mqtt_shared/pi-haven/state/myentity", "1") == ["1"]
        assert dispatcher.dispatch("mqtt_shared/pi-haven/state/BOGUS", "1") == []

        event_pattern2 = EventPattern("pi-haven", "state", None)
        dispatcher.add_listener("/pi-haven/state/+", event_pattern2, callback)
        assert dispatcher.dispatch("mqtt_shared/pi-haven/state/myentity", "1") == [
            "1",
            "1",
        ]
        assert dispatcher.dispatch("mqtt_shared/pi-haven/state/DIFFERENT", "1") == ["1"]

        self.log("**test_dispatcher() - all pass!**")
