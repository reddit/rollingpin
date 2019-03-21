import random

from twisted.internet.defer import inlineCallbacks, returnValue, succeed

from ..transports import (
    Transport,
    TransportConnection,
    CommandFailed,
)
from ..utils import sleep


class MockTransport(Transport):
    def __init__(self, config):
        pass

    @inlineCallbacks
    def connect_to(self, host):
        yield sleep(random.random())

        if host.startswith("noop"):
            connection = NoopDeployMockTransportConnection()
        else:
            connection = MockTransportConnection()

        returnValue(connection)


class MockTransportConnection(TransportConnection):
    @inlineCallbacks
    def execute(self, log, command, timeout=0):
        command, args = command[0], command[1:]

        if command == "synchronize":
            f = self._synchronize
        elif command == "build":
            f = self._build
        elif command == "deploy":
            f = self._deploy
        elif command == "restart":
            f = self._restart
        elif command == "wait-until-components-ready":
            f = self._wait
        elif command == "components":
            f = self._components
        else:
            raise CommandFailed("unknown command %r" % command)

        result = yield f(log, command, args)
        returnValue(result)

    def _synchronize(self, log, command, args):
        log.debug("MOCK: git fetch")
        return succeed({
            "test-component": {
                "token": "build-token",
                "buildhost": "build-01"
            }
        })

    def _build(self, log, command, args):
        result = dict()
        log.debug("MOCK: build stuff")
        for arg in args:
            result[arg] = "build-token"
        return succeed(result)

    def _deploy(self, log, command, args):
        for arg in args:
            (component, build_token) = arg.split("@")
            log.debug("MOCK: [{}] git fetch origin".format(component))
            if random.random() < .2:
                raise CommandFailed("remote command exited with status 127")
            log.debug("MOCK: [{}] git checkout {}".format(component, build_token))
            return succeed({})

    def _restart(self, log, command, args):
        log.debug("MOCK: /sbin/initctl emit restart")
        return succeed({})

    @inlineCallbacks
    def _wait(self, log, command, args):
        log.debug("MOCK: /sbin/initctl emit wait-until-components-ready")
        yield sleep(random.random() * 1)
        returnValue({})

    def _components(self, log, command, args):
        result = {
            "components": {
                "example": {
                    "fbcedda5b56618db18426f90a06f1f62984b95e8": 3,
                    "7af8fe6294eab579c022b200388e886a348f05ac": 5,
                },
            }
        }
        return succeed(result)

    def disconnect(self):
        return succeed(None)


class NoopDeployMockTransportConnection(MockTransportConnection):
    def _deploy(self, log, command, args):
        log.debug("MOCK: no local changes detected")
        result = dict()
        for arg in args:
            result[arg] = "repo_unchanged"

        return succeed(result)
