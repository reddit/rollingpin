import cStringIO as StringIO
import getpass
import json
import pipes
import struct

from twisted.conch.ssh.channel import SSHChannel
from twisted.conch.ssh.common import NS
from twisted.conch.ssh.connection import SSHConnection, EXTENDED_DATA_STDERR
from twisted.conch.ssh.keys import Key, EncryptedKeyError, BadKeyError
from twisted.conch.ssh.transport import SSHClientTransport
from twisted.conch.ssh.userauth import SSHUserAuthClient
from twisted.internet import reactor
from twisted.internet.defer import (
    Deferred,
    inlineCallbacks,
    returnValue,
    succeed,
)
from twisted.internet.error import ConnectError, DNSLookupError
from twisted.internet.protocol import ClientFactory

from ..config import Option
from ..transports import (
    Transport,
    TransportConnection,
    TransportError,
    CommandFailed,
    ConnectionError,
    ExecutionTimeout,
)


CONFIG_SPEC = {
    "transport": {
        "user": Option(str),
        "key": Option(str),
        "port": Option(int, default=22),
        "timeout": Option(int, default=10),
        "command": Option(str),
    },
}


class _ConnectionService(SSHConnection):
    def serviceStarted(self):
        self.transport.factory.state = "CONNECTED"
        self.transport.factory.connection_ready.callback(self)


class _ClientAuthService(SSHUserAuthClient):
    def __init__(self, factory, next_service):
        self.factory = factory
        self.config = factory.config
        user = self.config["transport"]["user"]
        SSHUserAuthClient.__init__(self, user, next_service)

    def getPassword(self, prompt=None):
        return

    def getPublicKey(self):
        if not self.lastPublicKey:
            public_key = self.factory.key.public()
            return succeed(public_key)

    def getPrivateKey(self):
        return succeed(self.factory.key)


class _ClientTransport(SSHClientTransport):
    def verifyHostKey(self, public_key, fingerprint):
        self.factory.state = "SECURING"
        return succeed(True)  # TODO

    def connectionSecure(self):
        self.factory.state = "AUTHENTICATING"
        next_service = _ConnectionService()
        auth_service = _ClientAuthService(self.factory, next_service)
        self.requestService(auth_service)

    def connectionLost(self, reason):
        if self.factory.state == "SECURING":
            error = ConnectError("unable to make a secure connection")
        elif self.factory.state == "AUTHENTICATING":
            error = ConnectError("unable to authenticate")
        elif self.factory.state == "CONNECTING":
            error = ConnectError("unable to connect")
        elif self.factory.state == "CONNECTED":
            return
        self.factory.connection_ready.errback(error)


class _ConnectionFactory(ClientFactory):
    protocol = _ClientTransport

    def __init__(self, config, key):
        self.connection_ready = Deferred()
        self.config = config
        self.key = key

    def clientConnectionFailed(self, connector, reason):
        self.connection_ready.errback(reason)


class BadKeyPassphraseError(TransportError):
    def __init__(self):
        TransportError.__init__(self, "bad passphrase for ssh key")


def _load_key(filename):
    try:
        return Key.fromFile(filename)
    except EncryptedKeyError:
        for i in xrange(3):
            passphrase = getpass.getpass("passphrase for %s: " % (filename,))
            if not passphrase:
                continue

            try:
                return Key.fromFile(filename, passphrase=passphrase)
            except BadKeyError:
                pass

        raise BadKeyPassphraseError()


class SshTransport(Transport):
    config_spec = CONFIG_SPEC

    def __init__(self, config):
        self.config = config

    def initialize(self):
        filename = self.config["transport"]["key"]
        self.key = _load_key(filename)

    @inlineCallbacks
    def connect_to(self, host):
        factory = _ConnectionFactory(self.config, self.key)
        factory.state = "CONNECTING"

        port = self.config["transport"]["port"]
        timeout = self.config["transport"]["timeout"]

        try:
            connector = reactor.connectTCP(
                host, port, factory, timeout=timeout)
            connection = yield factory.connection_ready
        except (ConnectError, DNSLookupError) as e:
            raise ConnectionError(str(e))

        command_binary = self.config["transport"]["command"]
        transport_connection = SshTransportConnection(
            command_binary, connector, connection)
        returnValue(transport_connection)


class ChannelError(CommandFailed):
    def __init__(self, reason):
        self.reason = reason
        super(ChannelError, self).__init__()

    def __str__(self):
        return "could not open command channel: %s" % self.reason


class NonZeroStatusError(CommandFailed):
    def __init__(self, status):
        self.status = status
        super(NonZeroStatusError, self).__init__()

    def __str__(self):
        return "remote command exited with status %d" % self.status


class SignalError(CommandFailed):
    def __init__(self, signal):
        self.signal = signal
        super(SignalError, self).__init__()

    def __str__(self):
        return "remote command was terminated by signal %d" % self.signal


class _CommandChannel(SSHChannel):
    name = "session"

    def __init__(self, log, command, timeout, *args, **kwargs):
        """
        :param timeout: command timeout in seconds.  0 for no timeout
        """
        self.log = log
        self.command = command
        self.finished = Deferred()
        self.result = StringIO.StringIO()
        self.reason = None
        self.timeout = timeout

        SSHChannel.__init__(self, *args, **kwargs)

    def _execution_timeout(self):
        if not self.finished.called:
            self.finished.errback(ExecutionTimeout(self.command))

    def channelOpen(self, data):
        if self.timeout:
            reactor.callLater(self.timeout, self._execution_timeout)
        command = self.command.encode("utf-8")
        self.conn.sendRequest(self, "exec", NS(command), wantReply=1)

    def openFailed(self, reason):
        self.conn.errback(ChannelError(reason.desc))

    def dataReceived(self, data):
        self.result.write(data)

    def extReceived(self, dataType, data):
        if dataType == EXTENDED_DATA_STDERR:
            # TODO: proper line buffering
            for line in data.splitlines():
                self.log.debug(line)

    def request_exit_status(self, data):
        (status,) = struct.unpack(">L", data)
        if status != 0:
            self.reason = NonZeroStatusError(status)

    def request_exit_signal(self, data):
        (signal,) = struct.unpack(">L", data)
        self.reason = SignalError(signal)

    def closed(self):

        # The `finished` callback may have been already called if there was a
        # timeout issue.  If we try to call it again, it will fail loudly with
        # a twisted `AlreadyCalledError` exception.
        if self.finished.called:
            return

        if not self.reason:
            self.result.seek(0)
            try:
                decoded = json.load(self.result)
            except ValueError:
                decoded = {}
            self.finished.callback(decoded)
        else:
            self.finished.errback(self.reason)


class SshTransportConnection(TransportConnection):
    def __init__(self, command_binary, connector, connection):
        self.command_binary = command_binary
        self.connector = connector
        self.connection = connection

    @inlineCallbacks
    def execute(self, log, command, timeout=0):
        args = " ".join(pipes.quote(part) for part in command)
        command = "sudo %s %s" % (self.command_binary, args)

        channel = _CommandChannel(
            log, command, conn=self.connection, timeout=timeout)
        self.connection.openChannel(channel)
        result = yield channel.finished
        returnValue(result)

    def disconnect(self):
        self.connector.disconnect()
        return succeed(None)
