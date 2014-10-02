import contextlib
import getpass
import logging
import posixpath
import urllib
import urlparse

from twisted.internet import reactor
from twisted.internet.defer import succeed, inlineCallbacks
from twisted.web.client import Agent, HTTPConnectionPool
from twisted.web.http_headers import Headers


class FormEncodedBodyProducer(object):
    def __init__(self, data):
        encoded = urllib.urlencode(
            {k: unicode(v).encode('utf-8') for k, v in data.iteritems()})
        self.length = len(encoded)
        self.body = encoded

    def startProducing(self, consumer):
        consumer.write(self.body)
        return succeed(None)

    def pauseProducing(self):
        pass

    def stopProducing(self):
        pass


class HaroldWhisperer(object):
    def __init__(self, config):
        self.base_url = config["harold"]["base-url"]
        self.secret = config["harold"]["secret"]

        self.connection_pool = HTTPConnectionPool(reactor)
        self.agent = Agent(reactor, pool=self.connection_pool)

    def make_request(self, path, data):
        base_url = urlparse.urlparse(self.base_url)
        path = posixpath.join("/harold", path, self.secret)
        url = urlparse.urlunparse((
            base_url.scheme,
            base_url.netloc,
            path,
            None,
            None,
            None
        ))

        body_producer = FormEncodedBodyProducer(data)
        headers = Headers({
            "User-Agent": ["deploy tool"],
            "Content-Type": ["application/x-www-form-urlencoded"],
        })
        return self.agent.request("POST", url, headers, body_producer)


@contextlib.contextmanager
def swallow_exceptions(log):
    try:
        yield
    except Exception as e:
        log.warning("harold: %s", e)


class HaroldNotifier(object):
    def __init__(self, harold, event_bus, word, hosts, command_line, log_path):
        self.log = logging.getLogger(__name__)
        self.harold = harold
        self.word = word
        self.hosts = dict.fromkeys(hosts, False)
        self.command_line = command_line
        self.log_path = log_path
        self.completed_hosts = 0

        event_bus.register({
            "deploy.begin": self.on_deploy_begin,
            "deploy.abort": self.on_deploy_abort,
            "deploy.end": self.on_deploy_end,
            "host.end": self.on_host_end,
        })

    @inlineCallbacks
    def on_deploy_begin(self):
        with swallow_exceptions(self.log):
            yield self.harold.make_request("deploy/begin", {
                "id": self.word,
                "who": getpass.getuser(),
                "args": self.command_line,
                "log_path": self.log_path,
                "count": len(self.hosts),
            })

    @inlineCallbacks
    def on_deploy_abort(self, reason):
        with swallow_exceptions(self.log):
            yield self.harold.make_request("deploy/abort", {
                "id": self.word,
                "reason": str(reason),
            })

    @inlineCallbacks
    def on_deploy_end(self):
        with swallow_exceptions(self.log):
            yield self.harold.make_request("deploy/end", {
                "id": self.word,
            })

    @inlineCallbacks
    def on_host_end(self, host):
        self.completed_hosts += 1

        with swallow_exceptions(self.log):
            yield self.harold.make_request("deploy/progress", {
                "id": self.word,
                "host": host,
                "index": self.completed_hosts,
            })


def enable_harold_notifications(
        word, config,  event_bus, hosts, command_line, log_path):
    harold = HaroldWhisperer(config)
    HaroldNotifier(harold, event_bus, word, hosts, command_line, log_path)
