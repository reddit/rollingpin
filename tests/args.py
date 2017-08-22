import unittest

from rollingpin.args import (
    make_arg_parser,
    make_profile_parser,
    construct_canonical_commandline,
)


class TestArgumentParsing(unittest.TestCase):

    def setUp(self):
        self.config = {
            "deploy": {
                "default-parallel": 5,
                "default-sleeptime": 2,
                "execution-timeout": 60,
            },

            "harold": {
                "base-url": "http://example.com",
                "secret": None,
            },
        }
        self.parser = make_arg_parser(self.config)

    # -h
    def test_no_args(self):
        with self.assertRaises(SystemExit):
            self.parser.parse_args(args=[])

    def test_host_list(self):
        args = self.parser.parse_args(["-h", "a", "b", "c"])
        self.assertEqual(args.host_refs, ["a", "b", "c"])

    def test_multiple_host_lists(self):
        args = self.parser.parse_args(["-h", "a", "-h", "b"])
        self.assertEqual(args.host_refs, ["a", "b"])

    # --parallel
    def test_parallel_default(self):
        args = self.parser.parse_args(["-h", "a"])
        self.assertEqual(args.parallel, 5)

    def test_parallel_override(self):
        args = self.parser.parse_args(["-h", "a", "--parallel", "3"])
        self.assertEqual(args.parallel, 3)

    # --sleeptime
    def test_sleeptime_default(self):
        args = self.parser.parse_args(["-h", "a"])
        self.assertEqual(args.sleeptime, 2)

    def test_sleeptime_override(self):
        args = self.parser.parse_args(["-h", "a", "--sleeptime", "1"])
        self.assertEqual(args.sleeptime, 1)

    # --startat
    def test_startat_empty(self):
        args = self.parser.parse_args(["-h", "a"])
        self.assertIsNone(args.start_at)

    def test_startat_host(self):
        args = self.parser.parse_args(["-h", "a", "--startat", "host"])
        self.assertEqual(args.start_at, "host")

    # --stopbefore
    def test_stopbefore_empty(self):
        args = self.parser.parse_args(["-h", "a"])
        self.assertIsNone(args.stop_before)

    def test_stopbefore_host(self):
        args = self.parser.parse_args(["-h", "a", "--stopbefore", "host"])
        self.assertEqual(args.stop_before, "host")

    # --pauseafter
    def test_pauseafter_not_set(self):
        args = self.parser.parse_args(["-h", "a"])
        self.assertEqual(args.pause_after, 1)

    def test_pauseafter_number(self):
        args = self.parser.parse_args(["-h", "a", "--pauseafter", "5"])
        self.assertEqual(args.pause_after, 5)

    # --list
    def test_list_default(self):
        args = self.parser.parse_args(["-h", "a"])
        self.assertFalse(args.list_hosts)

    def test_list_flagged(self):
        args = self.parser.parse_args(["-h", "a", "--list"])
        self.assertTrue(args.list_hosts)

    # --no-harold
    def test_harold_default(self):
        args = self.parser.parse_args(["-h", "a"])
        self.assertTrue(args.notify_harold)

    def test_harold_flagged(self):
        args = self.parser.parse_args(["-h", "a", "--no-harold"])
        self.assertFalse(args.notify_harold)

    # -v / --verbose
    def test_verbose_default(self):
        args = self.parser.parse_args(["-h", "a"])
        self.assertFalse(args.verbose_logging)

    def test_verbose_flagged_short(self):
        args = self.parser.parse_args(["-h", "a", "-v"])
        self.assertTrue(args.verbose_logging)

    def test_verbose_flagged_long(self):
        args = self.parser.parse_args(["-h", "a", "--verbose"])
        self.assertTrue(args.verbose_logging)

    # --dangerously-fast
    def test_dangerously_fast_default(self):
        args = self.parser.parse_args(["-h", "a"])
        self.assertFalse(args.dangerously_fast)

    def test_dangerously_fast_on(self):
        args = self.parser.parse_args(["-h", "a", "--dangerously-fast"])
        self.assertTrue(args.dangerously_fast)

    # -d
    def test_empty_deploys(self):
        args = self.parser.parse_args(["-h", "a"])
        self.assertEqual(args.components, [])

    def test_one_deploy(self):
        args = self.parser.parse_args(["-h", "a", "-d", "comp"])
        self.assertEqual(args.components, ["comp"])

    def test_double_deploy(self):
        args = self.parser.parse_args(["-h", "a", "-d", "comp", "comp2"])
        self.assertEqual(args.components, ["comp", "comp2"])

    def test_multiple_deploys(self):
        args = self.parser.parse_args(["-h", "a", "-d", "comp", "-d", "comp2"])
        self.assertEqual(args.components, ["comp", "comp2"])

    # -r
    def test_one_restart(self):
        args = self.parser.parse_args(["-h", "a", "-r", "all"])
        self.assertEqual(args.commands, [["restart", "all"]])

    def test_multi_restart(self):
        args = self.parser.parse_args(["-h", "a", "-r", "all", "-r", "more"])
        self.assertEqual(
            args.commands, [["restart", "all"], ["restart", "more"]])

    # -c
    def test_no_commands(self):
        args = self.parser.parse_args(["-h", "a"])
        self.assertEqual(args.commands, [])

    def test_simple_command(self):
        args = self.parser.parse_args(["-h", "a", "-c", "test"])
        self.assertEqual(args.commands, [["test"]])

    def test_command_with_args(self):
        args = self.parser.parse_args(["-h", "a", "-c", "test", "args"])
        self.assertEqual(args.commands, [["test", "args"]])

    # mixup
    def test_commands_together(self):
        args = self.parser.parse_args(
            ["-h", "a", "-c", "test", "args", "-r", "all"])
        self.assertEqual(args.commands, [["test", "args"], ["restart", "all"]])


class TestProfileArguments(unittest.TestCase):

    def setUp(self):
        self.config = {
            "deploy": {
                "default-parallel": 5,
                "default-sleeptime": 2,
                "execution-timeout": 60,
            },

            "harold": {
                "base-url": "http://example.com",
                "secret": None,
            },
        }
        self.profiles = ["foo", "bar", "baz"]
        self.profile_parser = make_profile_parser(available_profiles=self.profiles)
        self.parser = make_arg_parser(self.config, parent_parser=self.profile_parser)

    def test_profiles_arg(self):
        args = ["foo", "-h", "a", "-c", "test"]

        profile_info, _ = self.profile_parser.parse_known_args(args=args)

        full_args = self.parser.parse_args(args)

        self.assertEqual(profile_info.profile, "foo")
        self.assertEqual(full_args.commands, [["test"]])

    def test_invalid_profile(self):
        args = ["bad", "-h", "a"]

        with self.assertRaises(SystemExit):
            profile_info, _ = self.profile_parser.parse_known_args(args=args)


class TestArgumentReconstruction(unittest.TestCase):

    def setUp(self):
        self.config = {
            "deploy": {
                "default-parallel": 5,
                "default-sleeptime": 2,
                "execution-timeout": 60,
            },

            "harold": {
                "base-url": "http://example.com",
                "secret": None,
            },
        }
        self.parser = make_arg_parser(self.config)

    def test_single_host(self):
        args = self.parser.parse_args(["-h", "host"])
        canonical = construct_canonical_commandline(self.config, args)
        self.assertEqual("-h host --parallel=5 --timeout=60", canonical)

    def test_multiple_hosts(self):
        args = self.parser.parse_args(["-h", "host", "host2"])
        canonical = construct_canonical_commandline(self.config, args)
        self.assertEqual("-h host host2 --parallel=5 --timeout=60", canonical)

    def test_multiple_dash_hs(self):
        args = self.parser.parse_args(["-h", "host", "-h", "host2"])
        canonical = construct_canonical_commandline(self.config, args)
        self.assertEqual("-h host host2 --parallel=5 --timeout=60", canonical)

    def test_startat(self):
        args = self.parser.parse_args(["-h", "host", "--startat", "host"])
        canonical = construct_canonical_commandline(self.config, args)
        self.assertEqual(
            "-h host --startat=host --parallel=5 --timeout=60", canonical)

    def test_stopbefore(self):
        args = self.parser.parse_args(["-h", "host", "--stopbefore", "host"])
        canonical = construct_canonical_commandline(self.config, args)
        self.assertEqual(
            "-h host --stopbefore=host --parallel=5 --timeout=60", canonical)

    def test_parallel(self):
        args = self.parser.parse_args(["-h", "host", "--parallel", "1"])
        canonical = construct_canonical_commandline(self.config, args)
        self.assertEqual("-h host --parallel=1 --timeout=60", canonical)

    def test_sleeptime(self):
        args = self.parser.parse_args(["-h", "host", "--sleeptime", "5"])
        canonical = construct_canonical_commandline(self.config, args)
        self.assertEqual(
            "-h host --parallel=5 --sleeptime=5 --timeout=60", canonical)

    def test_pauseafter(self):
        args = self.parser.parse_args(["-h", "host", "--pauseafter", "2"])
        canonical = construct_canonical_commandline(self.config, args)
        self.assertEqual(
            "-h host --parallel=5 --pauseafter=2 --timeout=60", canonical)

    def test_no_harold(self):
        args = self.parser.parse_args(["-h", "host", "--no-harold"])
        canonical = construct_canonical_commandline(self.config, args)
        self.assertEqual(
            "-h host --parallel=5 --timeout=60 --no-harold", canonical)

    def test_single_deploy(self):
        args = self.parser.parse_args(["-h", "host", "-d", "component"])
        canonical = construct_canonical_commandline(self.config, args)
        self.assertEqual(
            "-h host --parallel=5 --timeout=60 -d component", canonical)

    def test_multiple_deploys(self):
        args = self.parser.parse_args(
            ["-h", "host", "-d", "component", "component2"])
        canonical = construct_canonical_commandline(self.config, args)
        self.assertEqual(
            "-h host --parallel=5 --timeout=60 -d component component2",
            canonical
        )

    def test_multiple_dash_ds(self):
        args = self.parser.parse_args(
            ["-h", "host", "-d", "component", "-d", "component2"])
        canonical = construct_canonical_commandline(self.config, args)
        self.assertEqual(
            "-h host --parallel=5 --timeout=60 -d component component2",
            canonical
        )

    def test_restart(self):
        args = self.parser.parse_args(["-h", "host", "-r", "component"])
        canonical = construct_canonical_commandline(self.config, args)
        self.assertEqual(
            "-h host --parallel=5 --timeout=60 -r component", canonical)

    def test_multi_restart(self):
        args = self.parser.parse_args(
            ["-h", "host", "-r", "com1", "-r", "com2"])
        canonical = construct_canonical_commandline(self.config, args)
        self.assertEqual(
            "-h host --parallel=5 --timeout=60 -r com1 -r com2", canonical)

    def test_simple_command(self):
        args = self.parser.parse_args(["-h", "host", "-c", "cmd"])
        canonical = construct_canonical_commandline(self.config, args)
        self.assertEqual("-h host --parallel=5 --timeout=60 -c cmd", canonical)

    def test_command_with_args(self):
        args = self.parser.parse_args(["-h", "host", "-c", "cmd", "arg"])
        canonical = construct_canonical_commandline(self.config, args)
        self.assertEqual(
            "-h host --parallel=5 --timeout=60 -c cmd arg", canonical)

    def test_multiple_commands(self):
        args = self.parser.parse_args(
            ["-h", "host", "-c", "cmd1", "-c", "cmd2"])
        canonical = construct_canonical_commandline(self.config, args)
        self.assertEqual(
            "-h host --parallel=5 --timeout=60 -c cmd1 -c cmd2", canonical)

    def test_verbose(self):
        args = self.parser.parse_args(["-h", "host", "-v"])
        canonical = construct_canonical_commandline(self.config, args)
        self.assertEqual(
            "-h host --parallel=5 --timeout=60 --verbose", canonical)
