import collections
import ConfigParser


NO_DEFAULT = object()


class Option(object):

    def __init__(self, coercer, default=NO_DEFAULT):
        self.coercer = coercer
        self.default = default


class OptionalSection(dict):

    def __init__(self, options):
        dict.__init__(self, options)


class ConfigurationError(Exception):

    def __init__(self, errors):
        self.errors = errors
        super(ConfigurationError, self).__init__()


class NoDefaultInOptionalSection(Exception):

    def __init__(self):
        Exception.__init__(
            self, "all options in an optional section must have defaults")


class MissingSectionError(object):

    def __init__(self, section):
        self.section = section

    def __str__(self):
        return "[%s]: section not found" % self.section


class MissingItemError(object):

    def __init__(self, section, key):
        self.section = section
        self.key = key

    def __str__(self):
        return "[%s]: %s: option not found" % (self.key, self.section)


class CoercionError(object):

    def __init__(self, section, key, error):
        self.section = section
        self.key = key
        self.error = error

    def __str__(self):
        return "[%s]: %s: %s" % (
            self.section, self.key, self.error)


def coerce_and_validate_config(parser, spec):
    config = collections.defaultdict(dict)
    errors = []

    for section_name, section_spec in spec.iteritems():
        section_optional = isinstance(section_spec, OptionalSection)
        if not (section_optional or parser.has_section(section_name)):
            errors.append(MissingSectionError(section_name))
            continue

        for key, option in section_spec.iteritems():
            if section_optional and option.default is NO_DEFAULT:
                raise NoDefaultInOptionalSection

            try:
                value = parser.get(section_name, key)
            except (ConfigParser.NoSectionError, ConfigParser.NoOptionError):
                if option.default is not NO_DEFAULT:
                    config[section_name][key] = option.default
                else:
                    errors.append(MissingItemError(section_name, key))
                continue

            try:
                coerced = option.coercer(value)
            except ValueError as e:
                errors.append(CoercionError(section_name, key, e))
            else:
                config[section_name][key] = coerced

    if errors:
        raise ConfigurationError(errors)

    return dict(config)
