import argparse
import os
import sys


class ExtendList(argparse.Action):
    def __call__(self, parser, namespace, values, option_string):
        list_to_extend = getattr(namespace, self.dest)
        if list_to_extend is self.default:
            # if the current value is the same ref as the default,
            # create a copy (so that extensions does not modify the
            # default value
            list_to_extend = self.default[:]
        if self.default:
            # if a default is defined, remove it before extending
            for default in self.default:
                list_to_extend.remove(default)
        list_to_extend.extend(values)
        setattr(namespace, self.dest, list_to_extend)


class RestartCommand(ExtendList):

    def __call__(self, parser, namespace, values, option_string):
        ExtendList.__call__(
            self, parser, namespace, [["restart", values]], option_string)


def _add_selection_arguments(config, parser):
    selection_group = parser.add_argument_group("host selection")

    default_hosts = config["deploy"].get("default-hosts", [])
    if not isinstance(default_hosts, list):
        default_hosts = [default_hosts]

    selection_group.add_argument(
        "-h",
        action=ExtendList,
        nargs="+",
        default=default_hosts,
        required=len(default_hosts) == 0,
        help="host(s) or group(s) to execute commands on",
        metavar="HOST",
        dest="host_refs",
    )


def _add_iteration_arguments(config, parser):
    iteration_group = parser.add_argument_group("host iteration")

    parallel_default = config["deploy"]["default-parallel"]
    iteration_group.add_argument(
        "--parallel",
        default=parallel_default,
        type=int,
        help="number of hosts to work on simultaneously (default: {})".format(
            parallel_default),
        metavar="COUNT",
        dest="parallel",
    )

    sleeptime_default = config["deploy"]["default-sleeptime"]
    iteration_group.add_argument(
        "--sleeptime",
        default=sleeptime_default,
        type=int,
        help="time in seconds to sleep between hosts (default: {})".format(
            sleeptime_default),
        metavar="SECONDS",
        dest="sleeptime",
    )

    timeout_default = config["deploy"]["execution-timeout"]
    iteration_group.add_argument(
        "--timeout",
        default=timeout_default,
        type=int,
        help="command execution timeout config override "
             "(default: {}, 0 for no timeout)".format(timeout_default),
        metavar="SECONDS",
        dest="timeout",
    )


def _add_flags(config, parser):
    options_group = parser.add_argument_group("options")

    options_group.add_argument(
        "--help",
        action="help",
        help="display this help",
    )

    options_group.add_argument(
        "--test",
        action="store_true",
        default=False,
        help="print out the full command format instead of running",
        dest="test",
    )

    options_group.add_argument(
        "--list",
        action="store_true",
        default=False,
        help="print a list of selected hosts and exit",
        dest="list_hosts",
    )

    options_group.add_argument(
        "--dangerously-fast",
        action="store_true",
        default=False,
        help="Deploy to all servers immediately and don't wait on restarts.",
        dest="dangerously_fast",
    )

    options_group.add_argument(
        "--no-harold",
        action="store_false",
        default=True,
        dest="deprecated_notify_harold",
    )
    if config["harold"]["base-url"]:
        options_group.add_argument(
            "--really-no-harold",
            action="store_false",
            default=True,
            help="don't notify harold of deploy status",
            dest="notify_harold",
        )
    else:
        options_group.add_argument(
            "--really-no-harold",
            action="store_false",
            default=False,
            help=argparse.SUPPRESS,
            dest="notify_harold",
        )

    options_group.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=False,
        help="spew verbose logging of command output to the console",
        dest="verbose_logging",
    )


def _add_deploy_arguments(config, parser):
    deploy_group = parser.add_argument_group(
        title="actions to execute on hosts",
        description=(
            "these actions will be executed on each host in the "
            "order specified on the command line."),
    )

    default_components = config["deploy"].get("default-components", [])
    if "," in default_components:
        default_components = default_components.split(",")

    if not isinstance(default_components, list):
        default_components = [default_components]

    deploy_group.add_argument(
        "-d",
        action=ExtendList,
        nargs="+",
        default=default_components,
        help="deploy the specified components",
        metavar="CMPNT",
        dest="components",
    )

    deploy_group.add_argument(
        "-r",
        action="append",
        default=[],
        help="whom to restart",
        metavar="TARGET",
        dest="restart",
    )

    deploy_group.add_argument(
        "-c",
        action="append",
        nargs="+",
        default=[],
        help="run a deploy command",
        metavar=("COMMAND", "ARG"),
        dest="commands",
    )


def parse_args(config, raw_args=None, profile=None):
    prog = os.path.basename(sys.argv[0])
    parser = argparse.ArgumentParser(
        prog="{} {}".format(prog, profile) if profile else prog,
        description="roll stuff to servers",
        add_help=False,
    )

    _add_selection_arguments(config, parser)
    _add_iteration_arguments(config, parser)
    _add_flags(config, parser)
    _add_deploy_arguments(config, parser)

    if not raw_args and not profile:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args(args=raw_args)

    if not args.restart:
        default_restart = config["deploy"].get("default-restart", [])
        if not isinstance(default_restart, list):
            default_restart = [default_restart]

        args.restart = default_restart

    for target in args.restart:
        args.commands.append(["restart", target])

    if args.components == ["none"]:
        args.components = []

    if not args.deprecated_notify_harold:
        print "--no-harold is deprecated now that profiles should direct to the correct harold"

    return args


def construct_canonical_commandline(config, args):
    arg_list = []

    arg_list.append("-h")
    arg_list.extend(args.host_refs)
    arg_list.append("--parallel=%d" % args.parallel)

    sleeptime_default = config["deploy"]["default-sleeptime"]
    if args.sleeptime != sleeptime_default:
        arg_list.append("--sleeptime=%d" % args.sleeptime)

    if args.timeout is not None:
        arg_list.append("--timeout=%d" % args.timeout)

    if config["harold"]["base-url"] and not args.notify_harold:
        arg_list.append("--really-no-harold")

    if args.verbose_logging:
        arg_list.append("--verbose")

    if args.dangerously_fast:
        arg_list.append("--dangerously-fast")

    if args.components:
        arg_list.append("-d")
        arg_list.extend(args.components)

    for command in args.commands:
        if command[0] == "restart":
            arg_list.extend(("-r", command[1]))
        else:
            arg_list.append("-c")
            arg_list.extend(command)

    return " ".join(arg_list)


def build_action_summary(config, args):
    expanded_command = (os.path.basename(sys.argv[0]) + " " +
                        construct_canonical_commandline(config, args))

    summary_points = []

    for component in args.components:
        summary_points.append("Deploy the `{}` component.".format(component))

    for command in args.commands:
        if command[0] == "restart":
            summary_points.append(
                "Restart `{}` applications.".format(command[1]))
        else:
            summary_points.append("Run the `{}` command.".format(" ".join(command)))

    summary_details = []

    for host in args.host_refs:
        summary_details.append("on `{}` hosts".format(host))

    summary_details.append("{} at a time".format(args.parallel))
    if args.timeout is not None:
        summary_details.append(
            "timing out if a host takes more than {} seconds".format(args.timeout))

    return "\n".join([expanded_command, "", "This will:", ""] +
                     ["* {}".format(p) for p in summary_points] +
                     ["", ', '.join(summary_details), ""])


def _get_available_profiles(profile_dir):
    profiles = []
    for f in os.listdir(profile_dir):
        if f.endswith(".ini"):
            profile_name, _ = f.split(".", 1)
            profiles.append(profile_name)

    return profiles


def make_profile_parser(profile_dir="/etc/rollingpin.d/"):
    parser = argparse.ArgumentParser(
        description="roll stuff to servers",
        add_help=False,
    )

    parser.add_argument(
        "profile",
        choices=_get_available_profiles(profile_dir),
        help="profile to run against",
    )

    return parser
