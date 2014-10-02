import random

from twisted.internet.defer import succeed

from ..hostsources import HostSource


class MockHostSource(HostSource):
    def __init__(self, config):
        pass

    def get_hosts(self):
        return succeed(
            ["host-%02d" % i for i in xrange(1, 270)] +
            ["otherhost-%02d" % i for i in xrange(1, 5)]
        )

    def should_be_alive(self, host):
        return succeed(random.choice((True, True, True, False)))
