import collections
import fnmatch
import itertools


ALIAS_SECTION = "aliases"


class HostlistError(Exception):
    pass


class UnresolvableAliasError(HostlistError):
    def __init__(self, glob):
        self.glob = glob
        super(UnresolvableAliasError, self).__init__()

    def __str__(self):
        return "unresolvable alias: %r matched no hosts" % self.glob


class UnresolvableHostRefError(HostlistError):
    def __init__(self, host_ref):
        self.host_ref = host_ref
        super(UnresolvableHostRefError, self).__init__()

    def __str__(self):
        return "no host or alias found for %r" % self.host_ref


class HostSelectionError(HostlistError):
    pass


def parse_aliases(config_parser):
    if not config_parser.has_section(ALIAS_SECTION):
        return {}

    aliases = {}
    for key, value in config_parser.items(ALIAS_SECTION):
        aliases[key] = value.split()
    return aliases


def resolve_aliases(unresolved_aliases, all_hosts):
    aliases = {}
    for alias, globs in unresolved_aliases.iteritems():
        hosts = []

        for glob in globs:
            globbed = fnmatch.filter(all_hosts, glob)
            if not globbed:
                raise UnresolvableAliasError(glob)
            hosts.extend(globbed)

        aliases[alias] = hosts
    return aliases


def resolve_hostlist(host_refs, all_hosts, aliases):
    unresolved_refs = collections.deque(host_refs)
    resolved_hosts = []

    while unresolved_refs:
        ref = unresolved_refs.popleft()

        if ref in aliases:
            resolved_hosts.extend(aliases[ref])
        elif ref in all_hosts:
            resolved_hosts.append(ref)
        else:
            raise UnresolvableHostRefError(ref)

    return resolved_hosts


def restrict_hostlist(hosts, start_at, stop_before):
    if start_at and start_at not in hosts:
        raise HostSelectionError(
            "--startat: %r not in host list" % start_at)

    if stop_before and stop_before not in hosts:
        raise HostSelectionError(
            "--stopbefore: %r not in host list" % stop_before)

    if start_at or stop_before:
        filtered = hosts
        if stop_before:
            filtered = itertools.takewhile(
                lambda host: host != stop_before, filtered)
        if start_at:
            filtered = itertools.dropwhile(
                lambda host: host != start_at, filtered)
        return list(filtered)
    else:
        return hosts
