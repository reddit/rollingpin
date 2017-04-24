from __future__ import division

import collections
import logging
import sys
import termios
import time
import tty

from twisted.internet.defer import (
    Deferred,
    DeferredList,
    inlineCallbacks,
    returnValue,
)
from twisted.internet.protocol import Protocol
from twisted.internet.stdio import StandardIO

from .deploy import AbortDeploy
from .utils import sorted_nicely


class Color(object):
    RED = "31"
    GREEN = "32"
    YELLOW = "33"
    BLUE = "34"
    MAGENTA = "35"
    CYAN = "36"
    WHITE = "37"

    @staticmethod
    def BOLD(color):
        return "1;" + color


def colorize(text, color):
    start = "\033[%sm" % color
    return start + text + "\033[0m"


COLOR_BY_LOGLEVEL = {
    logging.DEBUG: Color.WHITE,
    logging.INFO: Color.BOLD(Color.WHITE),
    logging.WARNING: Color.YELLOW,
    logging.ERROR: Color.BOLD(Color.RED),
}


class HostFormatter(logging.Formatter):

    def __init__(self, longest_hostname):
        self.hostname_format = "[%%%ds] " % (longest_hostname + 2)
        logging.Formatter.__init__(self)

    def format(self, record):
        formatted = logging.Formatter.format(self, record).decode("utf8")

        if hasattr(record, "host"):
            formatted = (self.hostname_format % record.host) + formatted

        color = COLOR_BY_LOGLEVEL[record.levelno]
        return colorize(formatted, color)


class HeadlessFrontend(object):

    def __init__(self, event_bus, hosts, verbose_logging):
        longest_hostname = max(len(host.name) for host in hosts)

        formatter = HostFormatter(longest_hostname)
        self.log_handler = logging.StreamHandler()
        self.log_handler.setFormatter(formatter)
        if verbose_logging:
            self.enable_verbose_logging()
        else:
            self.disable_verbose_logging()

            # temporarily boost logging during the build phase
            event_bus.register({
                "build.begin": self.enable_verbose_logging,
                "build.end": self.disable_verbose_logging,
            })

        root = logging.getLogger()
        root.addHandler(self.log_handler)

        self.host_results = {k: {} for k in hosts}
        self.start_time = None

        event_bus.register({
            "deploy.begin": self.on_deploy_begin,
            "deploy.end": self.on_deploy_end,
            "deploy.abort": self.on_deploy_abort,
            "host.end": self.on_host_end,
            "host.abort": self.on_host_abort,
        })

    def enable_verbose_logging(self):
        self.log_handler.setLevel(logging.DEBUG)

    def disable_verbose_logging(self):
        self.log_handler.setLevel(logging.INFO)

    def on_deploy_begin(self):
        self.start_time = time.time()
        print colorize("*** starting deploy", Color.BOLD(Color.GREEN))

    def count_hosts(self):
        return len(self.host_results)

    def count_completed_hosts(self):
        return sum(1 for v in self.host_results.itervalues() if v)

    def percent_complete(self):
        return (self.count_completed_hosts() / self.count_hosts()) * 100

    def on_host_end(self, host, results):
        if host in self.host_results:
            self.host_results[host]['status'] = "success"
            self.host_results[host]['results'] = results
            print colorize("*** %d%% done" % self.percent_complete(), Color.GREEN)  # noqa

    def on_host_abort(self, host, error, should_be_alive):
        if host in self.host_results:
            if should_be_alive:
                self.host_results[host]['status'] = "error"
            else:
                self.host_results[host]['status'] = "warning"

    def on_deploy_abort(self, reason):
        print colorize(
            "*** deploy aborted: %s" % reason, Color.BOLD(Color.RED))

    def on_deploy_end(self):
        by_result = collections.defaultdict(list)
        for host, result in self.host_results.iteritems():
            by_result[result['status']].append(host)

        print colorize("*** deploy complete!", Color.BOLD(Color.GREEN))

        if by_result["warning"]:
            warning_hosts = by_result["warning"]
            print("*** encountered errors on %d possibly terminated "
                  "hosts:" % len(warning_hosts))
            print "      ", " ".join(
                colorize(host, Color.YELLOW)
                for host in sorted_nicely(host.name for host in warning_hosts))

        if by_result["error"]:
            error_hosts = by_result["error"]
            print("*** encountered unexpected errors on %d "
                  "healthy hosts:" % len(error_hosts))
            print "      ", " ".join(
                colorize(host, Color.RED)
                for host in sorted_nicely(host.name for host in error_hosts))

        successful_hosts = len(by_result["success"])
        print "*** processed %d hosts successfully" % successful_hosts

        elapsed = time.time() - self.start_time
        print "*** elapsed time: %d seconds" % elapsed

        # TODO: Make this smarter.  It should only show anomolous
        # stuff.  Or maybe color that stuff differently.
        #
        # TODO: Check if component report was even requested before going
        # through them all?
        report = collections.defaultdict(lambda: collections.Counter())
        for host, results in self.host_results.iteritems():
            # Messed up hosts won't have results
            if 'results' not in results:
                continue
            for command, output in results['results']:
                if command[0] != 'components':
                    continue
                for component, sha in output['components'].iteritems():
                    report[component][sha] += 1
        if report:
            print colorize("*** component report", Color.BOLD(Color.GREEN))
            print "COMPONENT\tSHA\tCOUNT"
            for component in report.keys():
                for sha, count in report[component].iteritems():
                    print "%s\t%s\t%s" % (component, sha, count)


class StdioListener(Protocol):

    def __init__(self):
        self.character_waiter = Deferred()
        self.old_termio_settings = None

    def connectionMade(self):
        self.disable_echo()

    def disable_echo(self):
        fileno = sys.stdin.fileno()
        self.old_termio_settings = termios.tcgetattr(fileno)
        tty.setcbreak(fileno)

    def restore_terminal_settings(self):
        fileno = sys.stdin.fileno()
        termios.tcsetattr(fileno, termios.TCSADRAIN, self.old_termio_settings)

    def dataReceived(self, data):
        waiter = self.character_waiter
        self.character_waiter = Deferred()
        waiter.callback(data)

    def connectionLost(self, reason):
        self.restore_terminal_settings()

    @inlineCallbacks
    def read_character(self):
        while True:
            character = yield self.character_waiter
            if character:
                returnValue(character)

    @inlineCallbacks
    def raw_input(self, prompt):
        self.restore_terminal_settings()

        try:
            sys.stdout.write(prompt)
            sys.stdout.flush()

            line = yield self.character_waiter
            returnValue(line.rstrip("\n"))
        finally:
            self.disable_echo()


class HeadfulFrontend(HeadlessFrontend):

    def __init__(self, event_bus, hosts, verbose_logging, pause_after):
        HeadlessFrontend.__init__(self, event_bus, hosts, verbose_logging)

        self.console_input = StdioListener()
        StandardIO(self.console_input)

        event_bus.register({
            "deploy.sleep": self.on_sleep,
            "deploy.enqueue": self.on_enqueue,
        })

        self.pause_after = pause_after
        self.enqueued_hosts = 0

    def on_sleep(self, host, count):
        print colorize("*** sleeping %d..." % count, Color.BOLD(Color.BLUE))

    @inlineCallbacks
    def on_enqueue(self, deploys):
        # the deployer has added a host to the queue to deploy to
        self.enqueued_hosts += 1

        # we won't pause the action if we're near the end or have room for more
        completed_hosts = self.count_completed_hosts()
        if completed_hosts + self.pause_after >= self.count_hosts():
            return

        if not self.pause_after or self.enqueued_hosts < self.pause_after:
            return

        # wait for outstanding hosts to finish up
        yield DeferredList(deploys, consumeErrors=True)

        # prompt the user for what to do now
        while True:
            print colorize(
                "*** waiting for input: e[x]it, [c]ontinue, [a]ll remaining, "
                "[p]ercentage", Color.BOLD(Color.CYAN))

            c = yield self.console_input.read_character()

            if c == "a":
                self.pause_after = 0
                break
            elif c == "x":
                raise AbortDeploy("x pressed")
            elif c == "c":
                self.pause_after = 1
                break
            elif c == "p":
                min_percent = self.percent_complete() + 1
                prompt = "how far? (%d-100) " % min_percent
                prompt_input = yield self.console_input.raw_input(prompt)

                try:
                    desired_percent = int(prompt_input)
                except ValueError:
                    continue

                if not (min_percent <= desired_percent <= 100):
                    print("must be an integer between %d and 100" % min_percent)  # noqa
                    continue

                completed_hosts = self.count_completed_hosts()
                desired_host_index = int(
                    (desired_percent / 100) * self.count_hosts())
                self.pause_after = desired_host_index - completed_hosts
                break

        self.enqueued_hosts = 0
