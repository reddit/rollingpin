import ConfigParser
import unittest

from rollingpin.hostlist import (
    HostSelectionError,
    parse_aliases,
    resolve_aliases,
    resolve_hostlist,
    restrict_hostlist,
    UnresolvableAliasError,
    UnresolvableHostRefError,
)

from tests import make_configparser


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
        self.assertEqual(aliases, {"first": ["app-*", "job-*"], "second": ["none"]})


class TestAliasResolution(unittest.TestCase):
    def test_resolve_nothing(self):
        aliases = resolve_aliases({}, [])
        self.assertEqual(aliases, {})

    def test_resolve_direct_names(self):
        aliases = resolve_aliases({"a": ["b"]}, ["b"])
        self.assertEqual(aliases, {"a": ["b"]})

    def test_unsatisfied_glob(self):
        with self.assertRaises(UnresolvableAliasError):
            resolve_aliases({"a": ["b"]}, [])

    def test_glob(self):
        aliases = resolve_aliases({"a": ["a-*"]}, ["a-1", "a-2", "b-1"])
        self.assertEqual(aliases, {"a": ["a-1", "a-2"]})


class TestHostListResolution(unittest.TestCase):
    def test_empty(self):
        hostlist = resolve_hostlist([], [], {})
        self.assertEqual(hostlist, [])

    def test_simple_host(self):
        hostlist = resolve_hostlist(["a"], ["a"], {})
        self.assertEqual(hostlist, ["a"])

    def test_aliases(self):
        hostlist = resolve_hostlist(["alias"], ["a", "b", "c"], {"alias": ["a", "b"]})
        self.assertEqual(hostlist, ["a", "b"])

    def test_unknown_ref(self):
        with self.assertRaises(UnresolvableHostRefError):
            resolve_hostlist(["bad"], ["a", "b"], {})


class TestHostListRestriction(unittest.TestCase):
    def setUp(self):
        self.hostlist = ["a", "b", "c", "d", "e", "f"]

    def test_empty(self):
        hostlist = restrict_hostlist([], None, None)
        self.assertEqual(hostlist, [])

    def test_invalid_startat(self):
        with self.assertRaises(HostSelectionError):
            restrict_hostlist([], "a", None)

    def test_invalid_stopbefore(self):
        with self.assertRaises(HostSelectionError):
            restrict_hostlist([], None, "a")

    def test_startat(self):
        hostlist = restrict_hostlist(self.hostlist, "c", None)
        self.assertEqual(hostlist, ["c", "d", "e", "f"])

    def test_stopbefore(self):
        hostlist = restrict_hostlist(self.hostlist, None, "c")
        self.assertEqual(hostlist, ["a", "b"])

    def test_startat_and_stopbefore(self):
        hostlist = restrict_hostlist(self.hostlist, "c", "e")
        self.assertEqual(hostlist, ["c", "d"])

    def test_stopbefore_before_startat(self):
        hostlist = restrict_hostlist(self.hostlist, "e", "c")
        self.assertEqual(hostlist, [])
