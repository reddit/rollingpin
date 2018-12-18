"""Reports deploy metadata to elasticsearch"""
import getpass
import json
import logging
import time

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.web.client import Agent, readBody
from twisted.web.http_headers import Headers
from .utils import JSONBodyProducer, swallow_exceptions


class ElasticSearchNotifier(object):

    def __init__(self, config, components, hosts, command_line, word, profile):
        self.logger = logging.getLogger(__name__)
        base_url = config["elasticsearch"]["endpoint"]
        index = config["elasticsearch"]["index"]
        index_type = config["elasticsearch"]["type"]
        self.hosts = hosts
        self.command_line = command_line
        self.deploy_name = word
        self.profile = profile
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

    def update_doc(self, id_, updated_fields):
        """ Update a document in Elasticsearch
        :param updated_fields: dictionary values to update
        :return Deferred
        """
        # The twisted web client chokes on unicode URLs, so we'll coerce this
        # back to a string
        update_endpoint = str("%s/%s/_update" % (self.endpoint, id_))

        # Unlike indexing, for updates we have to put our updated fields inside
        # a "doc" key.
        #
        # https://www.elastic.co/guide/en/elasticsearch/guide/current/partial-updates.html
        doc = {'doc': updated_fields}

        with swallow_exceptions("elasticsearch", self.logger):
            agent = Agent(reactor)
            body = JSONBodyProducer(json.dumps(doc))
            return agent.request(
                'POST',
                update_endpoint,
                Headers({'User-Agent': ['rollingpin']}),
                body,
            )

    def build_sync_doc(self, sync_info):
        # We aren't aware of the commit ID that is being deployed at initial
        # deploy time.  Once the build sync has happened, we have this
        # information, so we go back and update the original document with a
        # list of the sync targets (i.e. commit IDs being deployed).
        sync = ["%s@%s" % (k, v.get('token', '')[:7])
                for k, v in sync_info.iteritems()]
        return {
            'sync_targets': ', '.join(sync),
        }

    def deploy_start_doc(self):
        timestamp_in_milliseconds = int(time.time()) * 1000
        return {
            'id': self.deploy_name,
            'profile': self.profile,
            'timestamp': timestamp_in_milliseconds,
            'components': self.components,
            'deployer': getpass.getuser(),
            'command': self.command_line,
            'hosts': self.hosts,
            'host_count': len(self.hosts),
            'event_type': 'deploy.begin',
        }

    def deploy_abort_doc(self, reason):
        timestamp_in_milliseconds = int(time.time()) * 1000
        return {
            'id': self.deploy_name,
            'profile': self.profile,
            'timestamp': timestamp_in_milliseconds,
            'reason': reason,
            'components': self.components,
            'event_type': 'deploy.abort',
        }

    def deploy_end_doc(self):
        timestamp_in_milliseconds = int(time.time()) * 1000
        return {
            'id': self.deploy_name,
            'profile': self.profile,
            'timestamp': timestamp_in_milliseconds,
            'components': self.components,
            'event_type': 'deploy.end',
        }

    @inlineCallbacks
    def on_build_sync(self, sync_info):
        yield self.update_doc(self.deploy_annotation_id,
                              self.build_sync_doc(sync_info))

    @inlineCallbacks
    def on_deploy_start(self):
        # Store the initial document's ID so we can update it with additional
        # metadata later in the deploy process.
        response = yield self.index_doc(self.deploy_start_doc())
        body = yield readBody(response)
        if response.code != 201:
            self.logger.error('Could not store deploy metadata.  '
                              'Got response %s', body)
        self.deploy_annotation_id = json.loads(body).get('_id', '')

    @inlineCallbacks
    def on_deploy_abort(self, reason):
        yield self.index_doc(self.deploy_abort_doc(reason))

    @inlineCallbacks
    def on_deploy_end(self):
        yield self.index_doc(self.deploy_end_doc())


def enable_elastic_search_notifications(config, event_bus, components, hosts,
                                        command_line, word, profile):
    notifier = ElasticSearchNotifier(
        config, components, hosts, command_line, word, profile)
    event_bus.register({
        "build.sync": notifier.on_build_sync,
        "deploy.begin": notifier.on_deploy_start,
        "deploy.abort": notifier.on_deploy_abort,
        "deploy.end": notifier.on_deploy_end,
    })
