import ConfigParser
import os
import sys

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet.task import react

from .elasticsearch import enable_elastic_search_notifications
from .args import make_arg_parser, construct_canonical_commandline
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
    resolve_aliases,
    resolve_hostlist,
    restrict_hostlist,
)
from .hostsources import HostSourceError
from .graphite import enable_graphite_notifications
from .log import log_to_file
from .providers import get_provider, UnknownProviderError
from .utils import random_word, interleaved


CONFIG_SPEC = {
    "deploy": {
        "log-directory": Option(str),
        "wordlist": Option(str),
        "code-host": Option(str),
        "default-sleeptime": Option(int),
        "default-parallel": Option(int),
    },

    "harold": OptionalSection({
        "base-url": Option(str, default=None),
        "hmac-secret": Option(str, default=None),
    }),

    "graphite": OptionalSection({
        "endpoint": Option(str, default=None),
    }),

    "elasticsearch": OptionalSection({
        "endpoint": Option(str, default=None),
        "index": Option(str, default=None),
        "type": Option(str, default=None),
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


def _load_configuration():
    config_parser = ConfigParser.ConfigParser()
    try:
        config_parser.read([
            "/etc/rollingpin.ini",
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


def _parse_args(config, raw_args):
    arg_parser = make_arg_parser(config)
    if not raw_args:
        arg_parser.print_help()
        sys.exit(0)
    args = arg_parser.parse_args(args=raw_args)
    args.original = construct_canonical_commandline(config, args)
    return args


@inlineCallbacks
def _select_hosts(config, args):
    # get the list of hosts from the host source
    try:
        all_hosts_unsorted = yield config["hostsource"].get_hosts()
    except HostSourceError as e:
        print_error("could not fetch host list: {}", e)
        sys.exit(1)

    hosts = interleaved(all_hosts_unsorted, key=lambda h: h.pool)

    try:
        aliases = resolve_aliases(config["aliases"], hosts)
        full_hostlist = resolve_hostlist(args.host_refs, hosts, aliases)
        selected_hosts = restrict_hostlist(
            full_hostlist, args.start_at, args.stop_before)
    except HostlistError as e:
        print_error("{}", e)
        sys.exit(1)

    returnValue(selected_hosts)


@inlineCallbacks
def _main(reactor, *raw_args):
    config = _load_configuration()
    args = _parse_args(config, raw_args)
    hosts = yield _select_hosts(config, args)

    # set up event listeners
    event_bus = EventBus()

    word = random_word(config["deploy"]["wordlist"])
    log_path = log_to_file(config, word)

    if args.notify_harold:
        enable_harold_notifications(
            word, config, event_bus, hosts,
            args.original, log_path)

    if config["graphite"]["endpoint"]:
        enable_graphite_notifications(config, event_bus, args.components)

    if config["elasticsearch"]["endpoint"]:
        enable_elastic_search_notifications(config, event_bus, args.components, hosts, args.original, word)

    if os.isatty(sys.stdout.fileno()):
        HeadfulFrontend(event_bus, hosts, args.verbose_logging, args.pause_after)
    else:
        HeadlessFrontend(event_bus, hosts, args.verbose_logging)

    # execute
    if args.list_hosts:
        for host in hosts:
            print host.name
    else:
        deployer = Deployer(config, event_bus, args.parallel, args.sleeptime)

        try:
            yield deployer.run_deploy(hosts, args.components, args.commands)
        except DeployError as e:
            print_error("{}", e)


def main():
    react(_main, sys.argv[1:])
