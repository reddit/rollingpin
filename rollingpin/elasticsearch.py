import json
import logging
import time

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, succeed
from twisted.web.client import Agent
from twisted.web.http_headers import Headers
from twisted.web.iweb import IBodyProducer
from zope.interface import implements
from .utils import swallow_exceptions


class JSONBodyProducer(object):
    implements(IBodyProducer)

    def __init__(self, data):
        self.length = len(data)
        self.body = data

    def startProducing(self, consumer):
        consumer.write(self.body)
        return succeed(None)

    def pauseProducing(self):
        pass

    def stopProducing(self):
        pass

    def getBody(self):
        return self.body


class ElasticSearchNotifier(object):
    def __init__(self, config, components):
        self.logger = logging.getLogger(__name__)
        base_url = config["elasticsearch"]["endpoint"]
        index = config["elasticsearch"]["index"]
        index_type = config["elasticsearch"]["type"]
        self.endpoint = "https://%s/%s/%s/_bulk" % (base_url, index, index_type)
        self.components = components

    @staticmethod
    def bulk_updates(components):
        now = int(time.time())
        actions = []
        for service in components:
            actions.append(json.dumps({'index': {}}))
            actions.append(json.dumps({
                'timestamp': now,
                'service': service
            }))
        return actions

    @staticmethod
    def request_body(components):
        """ Request body for bulk elastic search update
        Newline delimited JSON blobs with a newline after the last item
        """
        return "\n".join(ElasticSearchNotifier.bulk_updates(components)) + "\n"

    @inlineCallbacks
    def on_deploy_start(self):
        with swallow_exceptions("elasticsearch", self.logger):
            agent = Agent(reactor)
            body = JSONBodyProducer(self.request_body(self.components))
            yield agent.request(
                'POST',
                self.endpoint,
                Headers({'User-Agent': ['rollingpin']}),
                body
            )


def enable_elastic_search_notifications(config, event_bus, components):
    notifier = ElasticSearchNotifier(config, components)
    event_bus.register({
        "deploy.begin": notifier.on_deploy_start,
    })
