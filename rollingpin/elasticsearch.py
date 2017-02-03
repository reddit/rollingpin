"""Reports deploy metadata to elasticsearch"""
import getpass
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
    def __init__(self, config, components, hosts, command_line, word):
        self.logger = logging.getLogger(__name__)
        base_url = config["elasticsearch"]["endpoint"]
        index = config["elasticsearch"]["index"]
        index_type = config["elasticsearch"]["type"]
        self.hosts = hosts
        self.command_line = command_line
        self.deploy_name = word
        self.endpoint = "https://%s/%s/%s" % (base_url, index, index_type)
        self.components = components

    def index_doc(self, doc):
        """ Index a document in Elasticsearch
        :param doc: dictionary with data to index in ES
        :return: Deferred
        """
        with swallow_exceptions("elasticsearch", self.logger):
            agent = Agent(reactor)
            body = JSONBodyProducer(json.dumps(doc))
            return agent.request(
                'POST',
                self.endpoint,
                Headers({'User-Agent': ['rollingpin']}),
                body,
            )

    def deploy_start_doc(self):
        now = int(time.time())
        return {
            'id': self.deploy_name,
            'timestamp': now,
            'components': self.components,
            'deployer': getpass.getuser(),
            'command': self.command_line,
            'hosts': self.hosts,
            'host_count': len(self.hosts),
            'event_type': 'deploy.begin',
        }

    def deploy_abort_doc(self, reason):
        now = int(time.time())
        return {
            'id': self.deploy_name,
            'timestamp': now,
            'reason': reason,
            'event_type': 'deploy.abort',
        }

    def deploy_end_doc(self):
        now = int(time.time())
        return {
            'id': self.deploy_name,
            'timestamp': now,
            'event_type': 'deploy.end',
        }

    @inlineCallbacks
    def on_deploy_start(self):
        yield self.index_doc(self.deploy_start_doc())

    @inlineCallbacks
    def on_deploy_abort(self, reason):
        yield self.index_doc(self.deploy_abort_doc(reason))

    @inlineCallbacks
    def on_deploy_end(self):
        yield self.index_doc(self.deploy_end_doc())


def enable_elastic_search_notifications(config, event_bus, components, hosts, command_line, word):
    notifier = ElasticSearchNotifier(config, components, hosts, command_line, word)
    event_bus.register({
        "deploy.begin": notifier.on_deploy_start,
        "deploy.abort": notifier.on_deploy_abort,
        "deploy.end": notifier.on_deploy_end,
    })
