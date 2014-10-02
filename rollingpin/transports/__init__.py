class TransportError(Exception):
    pass


class ConnectionError(TransportError):
    pass


class Transport(object):
    def initialize(self):
        pass

    def connect_to(self, host):
        raise NotImplementedError


class CommandFailed(TransportError):
    pass


class TransportConnection(object):
    def execute(self, log, command):
        raise NotImplementedError

    def disconnect(self):
        raise NotImplementedError
