import collections

from twisted.internet.defer import inlineCallbacks, maybeDeferred


class EventBus(object):

    def __init__(self):
        self.mapping = collections.defaultdict(list)

    def register(self, event_map):
        for event, handler in event_map.iteritems():
            self.mapping[event].append(handler)

    @inlineCallbacks
    def trigger(self, event, **kwargs):
        for handler in self.mapping[event]:
            yield maybeDeferred(handler, **kwargs)
