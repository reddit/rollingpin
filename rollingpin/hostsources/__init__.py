class HostSourceError(Exception):
    pass


class HostSource(object):
    def get_hosts(self):
        raise NotImplementedError

    def should_be_alive(self, host):
        raise NotImplementedError
