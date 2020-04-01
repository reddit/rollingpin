"""Reports deploy metadata to Wavefront"""
import getpass
import json
import logging
import time
import urllib

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.web.client import Agent, readBody
from twisted.web.http_headers import Headers
from .utils import JSONBodyProducer, swallow_exceptions


class WavefrontNotifier(object):
    def __init__(self, config, components, hosts, command_line, word, profile):
        self.logger = logging.getLogger(__name__)
        self.endpoint = config['wavefront']['endpoint']
        self.hosts = hosts
        self.command_line = command_line
        self.deploy_name = word
        self.profile = profile
        self.api_key = config['wavefront']['api_key']
        self.components = components
        self.deploy_event_id = None
        self.deploy_start_time = None
        self.deploy_event = {
            "name": "%s Deploy" % self.profile,
            "annotations": {
                "severity": "info",
                "type": "Rollingpin Deploy",
                "details": "deploy-name=%s" % self.deploy_name,
            },
            "tags" : [
                "%s.deploy" % self.profile,
                "deploy",
            ],
        }

    def open_deploy_event(self, event_info):
        with swallow_exceptions('wavefront', self.logger):
            agent = Agent(reactor)
            body = JSONBodyProducer(json.dumps(event_info))
            return agent.request(
                'POST',
                '%s/api/v2/event' % self.endpoint,
                Headers({
                    'Authorization': ['Bearer %s' % self.api_key],
                    'Content-Type': ['application/JSON'],
                }),
                body,
            )

    def update_deploy_event(self, event_info):
        with swallow_exceptions('wavefront', self.logger):
            agent = Agent(reactor)
            body = JSONBodyProducer(json.dumps(event_info))
            return agent.request(
                'PUT',
                '%s/api/v2/event/%s' % (self.endpoint, urllib.quote(self.deploy_event_id)),
                Headers({
                    'Authorization': ['Bearer %s' % self.api_key],
                    'Content-Type': ['application/JSON'],
                }),
                body,
            )

    def deploy_start_event(self):
        """ Return Wavefront-conformant JSON indicating start of deploy.
        """
        timestamp_in_milliseconds = int(time.time()) * 1000
        self.deploy_start_time = timestamp_in_milliseconds
        self.deploy_event['startTime'] = self.deploy_start_time
        return self.deploy_event

    def deploy_abort_event(self, reason):
        """ Return Wavefront-conformant JSON to update deploy event
        indicating deploy was aborted.
        """
        timestamp_in_milliseconds = int(time.time()) * 1000
        self.deploy_event['annotations']['severity'] = 'warn'
        self.deploy_event['tags'].append("%s.deploy.aborted" % self.profile)
        self.deploy_event['endTime'] = timestamp_in_milliseconds
        return self.deploy_event

    def deploy_end_event(self):
        """ Return Wavefront-conformant JSON to update event
        indicating deploy was completed.
        """
        timestamp_in_milliseconds = int(time.time()) * 1000
        self.deploy_event['endTime'] = timestamp_in_milliseconds
        return self.deploy_event

    @inlineCallbacks
    def on_deploy_start(self):
        # Store initial event ID so we can update as deploy continues
        response = yield self.open_deploy_event(self.deploy_start_event())
        body = yield readBody(response)
        if response.code != 200:
            self.logger.error('Could not write Wavefront Event. '
                              ' Got response %s', body)
        self.deploy_event_id = json.loads(body)['response']['id']

    @inlineCallbacks
    def on_deploy_abort(self, reason):
        yield self.update_deploy_event(self.deploy_abort_event(reason))

    @inlineCallbacks
    def on_deploy_end(self):
        yield self.update_deploy_event(self.deploy_end_event())


def enable_wavefront_notifications(config, event_bus, components, hosts,
                                   command_line, word, profile):

    notifier = WavefrontNotifier(
        config, components, hosts, command_line, word, profile)
    event_bus.register({
        "deploy.begin": notifier.on_deploy_start,
        "deploy.abort": notifier.on_deploy_abort,
        "deploy.end": notifier.on_deploy_end,
    })
