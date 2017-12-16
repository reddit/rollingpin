import ConfigParser
import unittest

from rollingpin.hostlist import (
    HostSelectionError,
    parse_aliases,
    resolve_alias,
    resolve_hostlist,
    UnresolvableAliasError,
    UnresolvableHostRefError,
)

from tests import make_configparser


class MockHost(object):

    def __init__(self, name):
        self.name = name


class TestAliasParsing(unittest.TestCase):

    def test_no_section(self):
        empty_parser = ConfigParser.ConfigParser()
        aliases = parse_aliases(empty_parser)
        self.assertEqual(aliases, {})

    def test_no_aliases(self):
        section_only = make_configparser("[aliases]")
        aliases = parse_aliases(section_only)
        self.assertEqual(aliases, {})

    def test_parse_aliases(self):
        parser = make_configparser("""
        [aliases]
        first = app-* job-*
        second = none
        """)
        aliases = parse_aliases(parser)
        self.assertEqual(
            aliases, {"first": ["app-*", "job-*"], "second": ["none"]})


class TestAliasResolution(unittest.TestCase):

    def test_resolve_nothing(self):
        aliases = resolve_alias([], [])
        self.assertEqual(aliases, [])

    def test_resolve_direct_names(self):
        b = MockHost("b")
        hosts = resolve_alias([b], ["b"])
        self.assertEqual(hosts, [b])

    def test_unsatisfied_glob(self):
        with self.assertRaises(UnresolvableAliasError):
            resolve_alias([], ["a"])

    def test_glob(self):
        a_1, a_2, b_1 = MockHost("a-1"), MockHost("a-2"), MockHost("b-1")
        aliases = resolve_alias([a_1, a_2, b_1], ["a-*"])
        self.assertEqual(aliases, [a_1, a_2])


class TestHostListResolution(unittest.TestCase):

    def test_empty(self):
        hostlist = resolve_hostlist([], [], {})
        self.assertEqual(hostlist, [])

    def test_simple_host(self):
        a = MockHost("a")
        hostlist = resolve_hostlist(["a"], [a], {})
        self.assertEqual(hostlist, [a])

    def test_aliases(self):
        a, b, c = MockHost("a"), MockHost("b"), MockHost("c")
        hostlist = resolve_hostlist(["alias"], [a, b, c], {"alias": ["a", "b"]})
        self.assertEqual(hostlist, [a, b])

    def test_unknown_ref(self):
        with self.assertRaises(UnresolvableHostRefError):
            resolve_hostlist(["bad"], [MockHost("a"), MockHost("b")], {})

    def test_bad_unrelated_alias(self):
        a, b, c = MockHost("a"), MockHost("b"), MockHost("c")
        hostlist = resolve_hostlist(["good_alias"], [a, b, c], {
            "good_alias": "a",
            "bad_alias": "d",
        })
        self.assertEqual(hostlist, [a])
