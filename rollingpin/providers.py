import pkg_resources


class UnknownProviderError(Exception):

    def __init__(self, group, name):
        self.group = group
        self.name = name
        super(UnknownProviderError, self).__init__()

    def __str__(self):
        return "could not find provider %r for %s" % (self.name, self.group)


def get_provider(group, name):
    try:
        entry_point = pkg_resources.iter_entry_points(group, name).next()
    except StopIteration:
        raise UnknownProviderError(group, name)
    else:
        provider_cls = entry_point.load()
    return provider_cls
