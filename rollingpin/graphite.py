import time

from twisted.internet import endpoints, reactor
from twisted.internet.protocol import Protocol


class OneShotMessageWriter(Protocol):

    def __init__(self, message):
        self.message = message

    def connectionMade(self):
        self.transport.write(self.message)
        self.transport.loseConnection()


class GraphiteNotifier(object):

    def __init__(self, config, components):
        self.endpoint_config = config["graphite"]["endpoint"]
        self.components = components

    def on_deploy_start(self):
        now = int(time.time())
        events = ("events.deploy.%s %d %d\r\n" % (component, 1, now)
                  for component in self.components)
        message = "".join(events)
        protocol = OneShotMessageWriter(message)

        endpoint = endpoints.clientFromString(reactor, self.endpoint_config)
        endpoints.connectProtocol(endpoint, protocol)


def enable_graphite_notifications(config, event_bus, components):
    notifier = GraphiteNotifier(config, components)
    event_bus.register({
        "deploy.begin": notifier.on_deploy_start,
    })
