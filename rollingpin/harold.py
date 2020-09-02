import getpass
import hashlib
import hmac
import logging
import posixpath
import urllib

import urlparse
from twisted.internet import reactor
from twisted.internet.defer import succeed, inlineCallbacks
from twisted.web.client import Agent, HTTPConnectionPool
from twisted.web.http_headers import Headers

from .utils import swallow_exceptions

TIMEOUT_SECONDS = 5


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

    def hash(self, secret):
        return hmac.new(secret, self.body, hashlib.sha1).hexdigest()


class HaroldWhisperer(object):

    def __init__(self, config):
        self.base_url = config["harold"]["base-url"]
        self.secret = config["harold"]["hmac-secret"]

        self.log = logging.getLogger(__name__)
        self.connection_pool = HTTPConnectionPool(reactor)
        self.agent = Agent(reactor, connectTimeout=TIMEOUT_SECONDS, pool=self.connection_pool)

    def make_request(self, path, data):
        base_url = urlparse.urlparse(self.base_url)
        path = posixpath.join(base_url.path, "harold", path)
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
            "User-Agent": ["rollingpin"],
            "Content-Type": ["application/x-www-form-urlencoded"],
            "X-Hub-Signature": ["sha1=" + body_producer.hash(self.secret)],
        })
        req = self.agent.request("POST", url, headers, body_producer)

        def log_timeout(d, timeout):
            self.log.warning("harold: request timed out after %d seconds (/%s)", timeout, path)

        req.addTimeout(TIMEOUT_SECONDS, reactor, onTimeoutCancel=log_timeout)
        return req


class HaroldNotifier(object):

    def __init__(self, harold, event_bus, salon, word,
                 hosts, command_line, log_path):
        self.log = logging.getLogger(__name__)
        self.harold = harold
        self.salon = salon
        self.word = word
        self.command_line = command_line
        self.log_path = log_path
        self.total_hosts = len(hosts)
        self.completed_hosts = 0
        self.failed_hosts = []

        event_bus.register({
            "deploy.begin": self.on_deploy_begin,
            "deploy.abort": self.on_deploy_abort,
            "deploy.end": self.on_deploy_end,
            "host.end": self.on_host_end,
            "host.abort": self.on_host_abort,
        })

    @inlineCallbacks
    def on_deploy_begin(self):
        with swallow_exceptions("harold", self.log):
            yield self.harold.make_request("deploy/begin", {
                "salon": self.salon,
                "id": self.word,
                "who": getpass.getuser(),
                "args": self.command_line,
                "log_path": self.log_path,
                "count": self.total_hosts,
            })

    @inlineCallbacks
    def on_deploy_abort(self, reason):
        with swallow_exceptions("harold", self.log):
            yield self.harold.make_request("deploy/abort", {
                "salon": self.salon,
                "id": self.word,
                "reason": str(reason),
            })

    @inlineCallbacks
    def on_deploy_end(self):
        with swallow_exceptions("harold", self.log):
            yield self.harold.make_request("deploy/end", {
                "salon": self.salon,
                "id": self.word,
                "failed_hosts": ",".join(host.name for host in self.failed_hosts),
            })

    @inlineCallbacks
    def on_host_end(self, host, results):
        self.completed_hosts += 1

        with swallow_exceptions("harold", self.log):
            yield self.harold.make_request("deploy/progress", {
                "salon": self.salon,
                "id": self.word,
                "host": host,
                "index": self.completed_hosts,
            })

    def on_host_abort(self, host, error, should_be_alive):
        if should_be_alive:
            self.failed_hosts.append(host)


def enable_harold_notifications(
        word, config,  event_bus, hosts, command_line, log_path):
    if not (config["harold"]["base-url"] and
            config["harold"]["hmac-secret"] and
            config["harold"]["salon"]):
        return

    harold = HaroldWhisperer(config)
    HaroldNotifier(harold, event_bus, config["harold"]["salon"],
                   word, hosts, command_line, log_path)
