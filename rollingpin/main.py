import ConfigParser
import os
import sys
import warnings

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.task import react

from . import simpleflake
from .elasticsearch import enable_elastic_search_notifications
from .args import (
    parse_args,
    construct_canonical_commandline,
    make_profile_parser,
    build_action_summary,
)
from .config import (
    coerce_and_validate_config,
    ConfigurationError,
    Option,
    OptionalSection,
)
from .deploy import Deployer, DeployError
from .eventbus import EventBus
from .frontends import HeadlessFrontend, HeadfulFrontend
from .harold import enable_harold_notifications
from .hostlist import (
    HostlistError,
    parse_aliases,
    resolve_hostlist,
    select_canaries,
)
from .hostsources import HostSourceError
from .graphite import enable_graphite_notifications
from .log import log_to_file
from .providers import get_provider, UnknownProviderError
from .utils import interleaved, b36encode
from .wavefront import enable_wavefront_notifications


PROFILE_DIRECTORY = "/etc/rollingpin.d/"
CONFIG_SPEC = {
    "deploy": {
        "log-directory": Option(str),
        "wordlist": Option(str),
        "code-host": Option(str),
        "default-sleeptime": Option(int),
        "default-parallel": Option(int),
        "execution-timeout": Option(int, default=0),
        "default-hosts": Option(str, default=[]),
        "default-components": Option(str, default=[]),
        "default-restart": Option(str, default=[]),
    },

    "harold": OptionalSection({
        "base-url": Option(str, default=None),
        "hmac-secret": Option(str, default=None),
        "salon": Option(str, default=None),
    }),

    "graphite": OptionalSection({
        "endpoint": Option(str, default=None),
    }),

    "elasticsearch": OptionalSection({
        "endpoint": Option(str, default=None),
        "index": Option(str, default=None),
        "type": Option(str, default=None),
    }),

    "wavefront": OptionalSection({
        "endpoint": Option(str, default=None),
        "api_key": Option(str, default=None),
    }),

    "hostsource": {
        "provider": Option(str),
    },

    "transport": {
        "provider": Option(str),
    },
}


def print_error(message, *args, **kwargs):
    print >> sys.stderr, "{}: error: {}".format(
        os.path.basename(sys.argv[0]), message.format(*args, **kwargs))


def load_provider(provider_type, config_parser):
    group = "rollingpin.{}".format(provider_type)
    name = config_parser.get(provider_type, "provider")

    provider_cls = get_provider(group, name)

    if hasattr(provider_cls, "config_spec"):
        provider_config = coerce_and_validate_config(
            config_parser, provider_cls.config_spec)
    else:
        provider_config = {}

    return provider_cls(provider_config)


def _load_configuration(profile_name, profile_directory=PROFILE_DIRECTORY):
    config_parser = ConfigParser.ConfigParser()
    try:
        config_parser.read([
            "/etc/rollingpin.ini",
            "{}/{}.ini".format(profile_directory, profile_name),
            os.path.expanduser("~/.rollingpin.ini"),
        ])
    except ConfigParser.Error as e:
        print_error("could not parse configuration: {}", e)
        sys.exit(1)

    try:
        config = coerce_and_validate_config(config_parser, CONFIG_SPEC)
        config["hostsource"] = load_provider("hostsource", config_parser)
        config["transport"] = load_provider("transport", config_parser)
    except ConfigurationError as e:
        print_error("configuration invalid")
        for error in e.errors:
            print_error("{}", error)
        sys.exit(1)
    except UnknownProviderError as e:
        print_error("{}", e)
        sys.exit(1)

    config["aliases"] = parse_aliases(config_parser)
    return config


def _parse_args(config, raw_args, initial_parser):
    args = parse_args(config, raw_args, initial_parser)
    args.original = construct_canonical_commandline(config, args)
    return args


@inlineCallbacks
def _select_hosts(config, args):
    # get the list of hosts from the host source
    try:
        all_hosts = yield config["hostsource"].get_hosts()
    except HostSourceError as e:
        print_error("could not fetch host list: {}", e)
        sys.exit(1)

    try:
        hostlist = resolve_hostlist(args.host_refs, all_hosts, config["aliases"])
    except HostlistError as e:
        print_error("{}", e)
        sys.exit(1)

    canaries = select_canaries(hostlist)
    for canary in canaries:
        hostlist.remove(canary)

    # sort the list for repeatability across multiple deploys.
    sorted_hostlist = sorted(hostlist, key=lambda h: h.id, reverse=True)

    # interleave hosts by pool to spread pools out as evenly as possible
    rest_of_hosts = interleaved(sorted_hostlist, key=lambda h: h.pool)

    # the interleave algorithm biases to the left, so a small pool will be very
    # early in the list and nowhere near the end. since we touch one of each
    # host type in the canary process, we flip around the interleaved list
    # before concatenating to give the small pools more room before they are
    # repeated in the hostlist.
    returnValue(canaries + list(reversed(rest_of_hosts)))


@inlineCallbacks
def _main(reactor, *raw_args):
    # the crypto library now raises warnings about how twisted uses CTR mode on
    # the cypher used for SSH connections. we don't care and can't do anything
    # about it for now.
    warnings.simplefilter("ignore")
    initial_parser = make_profile_parser(PROFILE_DIRECTORY)
    if not raw_args:
        initial_parser.print_help()
        sys.exit(0)
    args, raw_args = initial_parser.parse_known_args(args=raw_args)
    profile = args.profile

    config = _load_configuration(profile, PROFILE_DIRECTORY)
    args = _parse_args(config, raw_args, profile)

    if not args.list_hosts:
        print build_action_summary(config, args)

    if args.test:
        sys.exit(0)

    hosts = yield _select_hosts(config, args)

    # set up event listeners
    event_bus = EventBus()

    word = b36encode(simpleflake.simpleflake())
    log_path = log_to_file(config, word)

    if args.notify_harold:
        enable_harold_notifications(
            word, config, event_bus, hosts,
            args.original, log_path)

    if config["graphite"]["endpoint"]:
        enable_graphite_notifications(config, event_bus, args.components)

    if config["elasticsearch"]["endpoint"]:
        enable_elastic_search_notifications(
            config, event_bus, args.components, hosts, args.original, word, profile)

    if config["wavefront"]["endpoint"] and config["wavefront"]["api_key"]:
        enable_wavefront_notifications(
            config, event_bus, args.components, hosts, args.original, word, profile)

    if not args.dangerously_fast and os.isatty(sys.stdout.fileno()):
        HeadfulFrontend(event_bus, hosts, args.verbose_logging, config)
    else:
        HeadlessFrontend(event_bus, hosts, args.verbose_logging)

    # execute
    if args.list_hosts:
        for host in hosts:
            print host.name, host.address
    else:
        deployer = Deployer(
            config,
            event_bus,
            args.parallel,
            args.sleeptime,
            args.timeout,
            args.dangerously_fast,
        )

        try:
            yield deployer.run_deploy(hosts, args.components, args.commands)
        except DeployError as e:
            print_error("{}", e)


def main():
    react(_main, sys.argv[1:])
