import random

from twisted.internet.defer import succeed

from ..config import Option
from ..hostsources import Host, HostSource


class MockHostSource(HostSource):
    config_spec = {
        "hostsource": {
            "hosts": Option(str),
        },
    }

    def __init__(self, config):
        self.hosts = config["hostsource"]["hosts"].split()

    def get_hosts(self):
        return succeed([Host(name, name, name, name.split("-")[0])
                        for name in self.hosts])

    def should_be_alive(self, host):
        return succeed(random.choice((True, True, True, False)))
