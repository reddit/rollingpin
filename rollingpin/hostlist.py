import fnmatch
import collections


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


def select_canaries(hosts):
    """Pick representative canary hosts from the full host list.

    The goals are:

    * the canaries should represent all pools in the hostlist
    * the first host should be from the most common pool
        * if it's a bad deploy it affects the pool with the most capacity.
        * hopefully the largest pool will have the most traffic to test on.
    * the ordering should be stable for repeatability on revert

    To achieve this, we take one host from each pool ordering the pools by
    descending size and the hosts within a pool by instance ID.

    """
    by_pool = collections.defaultdict(list)
    for host in hosts:
        by_pool[host.pool].append(host)

    by_pool_ordered_by_pool_size = sorted(
        by_pool.iteritems(),
        key=lambda (pool_name, hosts): len(hosts),
        reverse=True,
    )

    canaries = []
    for pool, hosts in by_pool_ordered_by_pool_size:
        canary_for_pool = sorted(hosts, key=lambda h: h.id)[0]
        canaries.append(canary_for_pool)
    return canaries
