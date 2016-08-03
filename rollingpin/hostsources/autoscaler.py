import collections
import logging
import posixpath
import math

import zookeeper
from twisted.internet.defer import (
    DeferredSemaphore,
    gatherResults,
    inlineCallbacks,
    returnValue,
)
from txzookeeper.client import ZookeeperClient

from ..config import Option
from ..hostsources import Host, HostSource, HostSourceError
from ..utils import sorted_nicely


MAX_PARALLELISM = 50


@inlineCallbacks
def parallel_map(iterable, fn, *args, **kwargs):
    deferreds = []
    parallelism_limiter = DeferredSemaphore(MAX_PARALLELISM)
    for item in iterable:
        d = parallelism_limiter.run(fn, item, *args, **kwargs)
        deferreds.append(d)
    results = yield gatherResults(deferreds)
    returnValue(results)


def _distribute_into(master, additions):
    assert len(master) >= len(additions)

    spread = int(math.ceil(float(len(master)) / len(additions)))

    for i, item in enumerate(additions):
        master.insert(i * spread, item)


def interleaved(by_pool):
    """Merge lists such that items from the same sublist are maximally apart.

    This ensures that no pool gets a bunch of its servers taken down all at
    the same time due to an unlucky host ordering.

    """
    pools_by_size = sorted(
        by_pool.items(), key=lambda t: len(t[1]), reverse=True)

    result = pools_by_size[0][1]
    for pool, hosts in pools_by_size[1:]:
        _distribute_into(result, hosts)
    return result


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
    def _get_host_info(self, hostname, by_pool, addresses):
        base_path = posixpath.join("/server", hostname)

        try:
            node = yield self.client.get(posixpath.join(base_path, "asg"))
        except zookeeper.NoNodeException:
            pool = ""
        else:
            pool = node[0]
        by_pool[pool].append(hostname)

        try:
            node = yield self.client.get(posixpath.join(base_path, "local-ipv4"))
        except zookeeper.NoNodeException:
            address = hostname
        else:
            address = node[0]
        addresses[hostname] = address

    @inlineCallbacks
    def get_hosts(self):
        try:
            yield self.client.connect()

            if self.user:
                yield self.client.add_auth(
                    "digest", "%s:%s" % (self.user, self.password))

            hostnames = yield self.client.get_children("/server")
            hostnames = sorted_nicely(hostnames)

            by_pool = collections.defaultdict(list)
            addresses = {}
            yield parallel_map(hostnames, self._get_host_info, by_pool, addresses)

            pool_aware = interleaved(by_pool)
            returnValue(Host(name, addresses[name]) for name in pool_aware)
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
                "autoscaler: failed to check liveliness for %r: %s", host.name, e)
            returnValue(True)
