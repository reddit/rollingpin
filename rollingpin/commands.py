from abc import ABCMeta, abstractproperty


class Command(object):
    __metaclass__ = ABCMeta

    def __init__(self, args=None):
        if args is None:
            self._args = []
        else:
            self._args = args

    def add_argument(self, arg):
        self._args.append(arg)

    @abstractproperty
    def name(self):
        raise NotImplementedError

    @property
    def args(self):
        return self._args

    def cmdline(self):
        return [self.name()] + self._args


class SynchronizeCommand(Command):
    def name(self):
        return "synchronize"


class DeployCommand(Command):
    def name(self):
        return "deploy"


class BuildCommand(Command):
    def name(self):
        return "build"


class RestartCommand(Command):
    def name(self):
        return "restart"


class WaitUntilComponentsReadyCommand(Command):
    def name(self):
        return "wait-until-components-ready"
