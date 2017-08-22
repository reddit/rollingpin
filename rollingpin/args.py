import argparse
import os


PAUSEAFTER_DEFAULT = 1


class ExtendList(argparse.Action):

    def __call__(self, parser, namespace, values, option_string):
        list_to_extend = getattr(namespace, self.dest)
        list_to_extend.extend(values)
        setattr(namespace, self.dest, list_to_extend)


class RestartCommand(ExtendList):

    def __call__(self, parser, namespace, values, option_string):
        ExtendList.__call__(
            self, parser, namespace, [["restart", values]], option_string)


def _add_selection_arguments(config, parser):
    selection_group = parser.add_argument_group("host selection")
    default_hosts = config["deploy"].get("hosts", [])
    if not isinstance(default_hosts, list):
        default_hosts = [default_hosts]

    selection_group.add_argument(
        "-h",
        action=ExtendList,
        nargs="+",
        default=default_hosts,
        required=True,
        help="host(s) or group(s) to execute commands on",
        metavar="HOST",
        dest="host_refs",
    )

    selection_group.add_argument(
        "--startat",
        help="skip to this position in the host list",
        metavar="HOST",
        dest="start_at",
    )

    selection_group.add_argument(
        "--stopbefore",
        help="end the deploy when this host is reached",
        metavar="HOST",
        dest="stop_before",
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

    iteration_group.add_argument(
        "--pauseafter",
        default=PAUSEAFTER_DEFAULT,
        type=int,
        help="pause after COUNT hosts",
        metavar="COUNT",
        dest="pause_after",
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
        help=("Don't wait on service restarts."
              "VERY dangerous when combined with a high parallel host count"
              ),
        dest="dangerously_fast",
    )

    if config["harold"]["base-url"]:
        options_group.add_argument(
            "--no-harold",
            action="store_false",
            default=True,
            help="don't notify harold of deploy status",
            dest="notify_harold",
        )
    else:
        options_group.add_argument(
            "--no-harold",
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

    default_components = config["deploy"].get("components", [])
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

    default_restarts = config["deploy"].get("restarts", [])
    if not isinstance(default_restarts, list):
        default_restarts = [default_restarts]

    deploy_group.add_argument(
        "-r",
        action=RestartCommand,
        default=default_restarts,
        help="whom to restart",
        metavar="TARGET",
        dest="commands",
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


def make_arg_parser(config, parent_parser=None):
    parser = argparse.ArgumentParser(
        parents=[parent_parser] if parent_parser else [],
        description="roll stuff to servers",
        add_help=False,
    )

    _add_selection_arguments(config, parser)
    _add_iteration_arguments(config, parser)
    _add_flags(config, parser)
    _add_deploy_arguments(config, parser)

    return parser


def construct_canonical_commandline(config, args):
    arg_list = []

    arg_list.append("-h")
    arg_list.extend(args.host_refs)

    if args.start_at:
        arg_list.append("--startat=%s" % args.start_at)

    if args.stop_before:
        arg_list.append("--stopbefore=%s" % args.stop_before)

    arg_list.append("--parallel=%d" % args.parallel)

    sleeptime_default = config["deploy"]["default-sleeptime"]
    if args.sleeptime != sleeptime_default:
        arg_list.append("--sleeptime=%d" % args.sleeptime)

    if args.pause_after != PAUSEAFTER_DEFAULT:
        arg_list.append("--pauseafter=%d" % args.pause_after)

    if args.timeout is not None:
        arg_list.append("--timeout=%d" % args.timeout)

    if config["harold"]["base-url"] and not args.notify_harold:
        arg_list.append("--no-harold")

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


def _get_available_profiles(profile_dir):
    profiles = []
    for f in os.listdir(profile_dir):
        if f.endswith(".ini"):
            profile_name, _ = f.split(".", 1)
            profiles.append(profile_name)

    return profiles

def make_profile_parser(profile_dir="/etc/rollingpin.d/",
                        available_profiles=None):
    parser = argparse.ArgumentParser(
        description="roll stuff to servers",
        add_help=False,
    )

    parser.add_argument(
        "profile",
        choices=available_profiles or _get_available_profiles(profile_dir),
        help="profile to run against",
    )

    return parser
