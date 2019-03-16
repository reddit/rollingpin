class Command(object):
    CONTINUE = 1
    SKIP_REMAINING = 2

    def __init__(self, args=None, explicit=False):
        self.explicit = explicit
        self._args = args or []

    @property
    def args(self):
        return self._args

    def add_argument(self, arg):
        self._args.append(arg)

    def cmdline(self):
        return [self.name] + self._args

    def check_result(self, result):
        return Command.CONTINUE

    def __repr__(self):
        return "Command(name={}, args={})".format(self.name, self._args)


class SynchronizeCommand(Command):
    name = "synchronize"


class DeployCommand(Command):
    # Flag constants for deploy return value
    REPO_UNCHANGED = "repo_unchanged"
    REPO_CHANGED = "repo_changed"

    name = "deploy"

    def check_result(self, result):
        # For backwards compatibility
        if not result:
            return Command.CONTINUE

        changed = any(result[v] == DeployCommand.REPO_CHANGED for v in result)
        if not changed:
            return Command.SKIP_REMAINING
        else:
            return Command.CONTINUE


class BuildCommand(Command):
    name = "build"


class RestartCommand(Command):
    name = "restart"


class WaitUntilComponentsReadyCommand(Command):
    name = "wait-until-components-ready"


class GenericCommand(Command):

    def __init__(self, name, args=None):
        self.name = name
        # Generic commands can only be added explicitly from the commandline.
        super(GenericCommand, self).__init__(args=args, explicit=True)
