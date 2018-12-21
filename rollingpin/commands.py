from abc import ABCMeta, abstractproperty


class Command(object):
    __metaclass__ = ABCMeta

    CONTINUE = 1
    SKIP_REMAINING = 2

    def __init__(self, args=None):
        if args is None:
            self._args = []
        else:
            self._args = args

    @abstractproperty
    def name(self):
        raise NotImplementedError

    @property
    def args(self):
        return self._args

    def add_argument(self, arg):
        self._args.append(arg)

    def cmdline(self):
        return [self.name()] + self._args

    def check_result(self, result):
        return Command.CONTINUE

    def __str__(self):
        return "Command(name={}, args={})".format(self.name(), self._args)

    def __repr__(self):
        return self.__str__()


class SynchronizeCommand(Command):
    def name(self):
        return "synchronize"


class DeployCommand(Command):
    def name(self):
        return "deploy"

    def check_result(self, result):
        # For backwards compatibility
        if not result:
            return Command.CONTINUE

        changed = any([result[v] is not False for v in result])
        if not changed:
            return Command.SKIP_REMAINING
        else:
            return Command.CONTINUE


class BuildCommand(Command):
    def name(self):
        return "build"


class RestartCommand(Command):
    def name(self):
        return "restart"


class WaitUntilComponentsReadyCommand(Command):
    def name(self):
        return "wait-until-components-ready"


class GenericCommand(Command):
    def __init__(self, name, args=None):
        self._name = name
        super(GenericCommand, self).__init__(args)

    def name(self):
        return self._name
