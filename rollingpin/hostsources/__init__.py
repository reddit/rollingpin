import collections


class HostSourceError(Exception):
    pass


_Host = collections.namedtuple("_Host", "id name address pool")


class Host(_Host):
    @classmethod
    def from_hostname(cls, name):
        return Host(name, name, name, "")


class HostSource(object):
    def get_hosts(self):
        raise NotImplementedError

    def should_be_alive(self, host):
        raise NotImplementedError
