import unittest

from twisted.internet.defer import Deferred

from rollingpin.eventbus import EventBus


class TestEvents(unittest.TestCase):

    def test_empty_bus(self):
        bus = EventBus()
        bus.trigger("noodle")

    def test_single_event(self):
        self.was_fired = False

        def callback():
            self.was_fired = True

        bus = EventBus()
        bus.register({
            "noodle": callback,
        })
        bus.trigger("noodle")
        self.assertTrue(self.was_fired)

    def test_multiple_for_event(self):
        self.count = 0

        def callback():
            self.count += 1

        bus = EventBus()
        bus.register({"noodle": callback})
        bus.register({"noodle": callback})
        bus.trigger("noodle")
        self.assertEqual(self.count, 2)

    def test_args_passed_through(self):
        self.got_argument = False

        def callback(argument=False):
            self.got_argument = argument

        bus = EventBus()
        bus.register({
            "noodle": callback,
        })
        bus.trigger("noodle", argument=True)
        self.assertTrue(self.got_argument)


class TestDeferredEvents(unittest.TestCase):

    def test_returned_deferred(self):
        d = Deferred()

        def callback():
            return d

        bus = EventBus()
        bus.register({"noodle": callback})
        trigger_deferred = bus.trigger("noodle")

        self.was_original_deferred_fired_yet = False

        def other_callback(result):
            self.assertTrue(self.was_original_deferred_fired_yet)
        trigger_deferred.addCallback(other_callback)

        self.was_original_deferred_fired_yet = True
        d.callback(None)
