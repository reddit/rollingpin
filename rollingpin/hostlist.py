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


def resolve_alias(all_hosts, globs):
    hosts = []

    for glob in globs:
        globbed = [host for host in all_hosts
                   if fnmatch.fnmatch(host.name, glob)]
        if not globbed:
            raise UnresolvableAliasError(glob)
        hosts.extend(globbed)
    return hosts


def resolve_hostlist(host_refs, all_hosts, aliases):
    resolved_hosts = []

    for ref in host_refs:
        if ref in aliases:
            hosts = resolve_alias(all_hosts, aliases[ref])
            resolved_hosts.extend(hosts)
        else:
            matching_hosts = [host for host in all_hosts if host.name == ref]

            if matching_hosts:
                resolved_hosts.extend(matching_hosts)
            else:
                raise UnresolvableHostRefError(ref)

    return resolved_hosts


def restrict_hostlist(hosts, start_at, stop_before):
    if start_at and not any(host.name == start_at for host in hosts):
        raise HostSelectionError(
            "--startat: %r not in host list" % start_at)

    if stop_before and not any(host.name == stop_before for host in hosts):
        raise HostSelectionError(
            "--stopbefore: %r not in host list" % stop_before)

    if start_at or stop_before:
        filtered = hosts
        if stop_before:
            filtered = itertools.takewhile(
                lambda host: host.name != stop_before, filtered)
        if start_at:
            filtered = itertools.dropwhile(
                lambda host: host.name != start_at, filtered)
        return list(filtered)
    else:
        return hosts
