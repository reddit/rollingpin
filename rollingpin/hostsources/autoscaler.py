import logging
import posixpath

import zookeeper
from twisted.internet.defer import (
    gatherResults,
    inlineCallbacks,
    returnValue,
)
from txzookeeper.client import ZookeeperClient

from ..config import Option
from ..hostsources import Host, HostSource, HostSourceError
from ..utils import parallel_map


class AutoscalerHostSource(HostSource):
    config_spec = {
        "hostsource": {
            "connection-string": Option(str),
            "user": Option(str, default=None),
            "password": Option(str, default=None),
        },
    }

    def __init__(self, config):
        # zoopy is really friggin' loud without this
        zookeeper.set_debug_level(0)

        connection_string = config["hostsource"]["connection-string"]
        self.client = ZookeeperClient(connection_string, session_timeout=3000)
        self.user = config["hostsource"]["user"]
        self.password = config["hostsource"]["password"]

    @inlineCallbacks
    def _get_host_info(self, hostname):
        base_path = posixpath.join("/server", hostname)

        try:
            node = yield self.client.get(posixpath.join(base_path, "asg"))
        except zookeeper.NoNodeException:
            pool = ""
        else:
            pool = node[0]

        try:
            ipv4 = posixpath.join(base_path, "local-ipv4")
            node = yield self.client.get(ipv4)
        except zookeeper.NoNodeException:
            address = hostname
        else:
            address = node[0]

        returnValue(Host(hostname, hostname, address, pool))

    @inlineCallbacks
    def get_hosts(self):
        try:
            yield self.client.connect()

            if self.user:
                yield self.client.add_auth(
                    "digest", "%s:%s" % (self.user, self.password))

            hostnames = yield self.client.get_children("/server")
            hosts = yield parallel_map(hostnames, self._get_host_info)
            returnValue(hosts)
        except zookeeper.ZooKeeperException as e:
            raise HostSourceError(e)

    @inlineCallbacks
    def should_be_alive(self, host):
        host_root = "/server/%s" % host.name

        try:
            state = yield self.client.get(host_root + "/state")

            if state in ("kicking", "unhealthy"):
                returnValue(False)

            is_autoscaled = yield self.client.exists(host_root + "/asg")
            is_running = yield self.client.exists(host_root + "/running")
            returnValue(not bool(is_autoscaled) or bool(is_running))
        except zookeeper.NoNodeException:
            # ok, it's just a bad node
            returnValue(False)
        except zookeeper.ZooKeeperException as e:
            # fail safe
            logging.warning(
                "autoscaler: failed to check liveliness for %r: %s",
                host.name,
                e
            )
            returnValue(True)
