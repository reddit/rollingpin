class TransportError(Exception):
    pass


class ConnectionError(TransportError):
    pass


class ExecutionTimeout(TransportError):

    def __init__(self, command):
        self.command = command
        super(ExecutionTimeout, self).__init__()

    def __str__(self):
        return "Timed out executing command %r" % (self.command)


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
