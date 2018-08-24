import json
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


class HippoHostSource(HostSource):
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
    def _get_host_info(self, instance_id):
        host_node_path = posixpath.join("/hosts", instance_id)
        try:
            host_json, znode = yield self.client.get(host_node_path)
        except zookeeper.NoNodeException:
            returnValue(None)

        host_info = json.loads(host_json)
        tags = host_info["properties"]["tags"]
        try:
            hostname = tags["HostClass"] + instance_id[1:]
        except KeyError:
            try:
                hostname = tags["Name"]
            except KeyError:
                hostname = instance_id

        address = host_info["properties"]["private_ip"]
        pool = tags.get("aws:autoscaling:groupName", "")

        returnValue(Host(instance_id, hostname, address, pool))

    @inlineCallbacks
    def get_hosts(self):
        try:
            yield self.client.connect()

            if self.user:
                yield self.client.add_auth(
                    "digest", "%s:%s" % (self.user, self.password))

            instance_ids = yield self.client.get_children("/hosts")
            hosts = yield parallel_map(instance_ids, self._get_host_info)
            returnValue(filter(None, hosts))
        except zookeeper.ZooKeeperException as e:
            raise HostSourceError(e)

    @inlineCallbacks
    def should_be_alive(self, host):
        instance_root = "/hosts/%s" % host.id

        try:
            yield self.client.get(instance_root)
            returnValue(True)
        except zookeeper.NoNodeException:
            # ok, it's just a bad node
            returnValue(False)
        except zookeeper.ZooKeeperException as e:
            # fail safe
            logging.warning(
                "hippo: failed to check liveliness for %r: %s", host.name, e)
            returnValue(True)
