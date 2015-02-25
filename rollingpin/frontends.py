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
        formatted = logging.Formatter.format(self, record)

        if hasattr(record, "host"):
            formatted = (self.hostname_format % record.host) + formatted

        color = COLOR_BY_LOGLEVEL[record.levelno]
        return colorize(formatted, color)


class HeadlessFrontend(object):
    def __init__(self, event_bus, hosts, verbose_logging):
        longest_hostname = max(len(host) for host in hosts)

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

        self.host_results = dict.fromkeys(hosts, None)
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

    def on_host_end(self, host):
        if host in self.host_results:
            self.host_results[host] = "success"

            complete_hosts = sum(1 for v in self.host_results.itervalues() if v)
            percent = (float(complete_hosts) / len(self.host_results)) * 100
            print colorize("*** %d%% done" % percent, Color.GREEN)

    def on_host_abort(self, host, error, should_be_alive):
        if host in self.host_results:
            if should_be_alive:
                self.host_results[host] = "error"
            else:
                self.host_results[host] = "warning"

    def on_deploy_abort(self, reason):
        print colorize(
            "*** deploy aborted: %s" % reason, Color.BOLD(Color.RED))

    def on_deploy_end(self):
        by_result = collections.defaultdict(list)
        for host, result in self.host_results.iteritems():
            by_result[result].append(host)

        print colorize("*** deploy complete!", Color.BOLD(Color.GREEN))

        if by_result["warning"]:
            warning_hosts = by_result["warning"]
            print ("*** encountered errors on %d possibly terminated "
                   "hosts:" % len(warning_hosts))
            print "      ", " ".join(
                colorize(host, Color.YELLOW)
                for host in sorted_nicely(warning_hosts))

        if by_result["error"]:
            error_hosts = by_result["error"]
            print ("*** encountered unexpected errors on %d "
                   "healthy hosts:" % len(error_hosts))
            print "      ", " ".join(
                colorize(host, Color.RED)
                for host in sorted_nicely(error_hosts))

        successful_hosts = len(by_result["success"])
        print "*** processed %d hosts successfully" % successful_hosts

        elapsed = time.time() - self.start_time
        print "*** elapsed time: %d seconds" % elapsed


class StdioListener(Protocol):
    def __init__(self):
        self.character_waiter = Deferred()
        self.old_termio_settings = None

    def connectionMade(self):
        # go to single-character, no-echo mode
        fileno = sys.stdin.fileno()
        self.old_termio_settings = termios.tcgetattr(fileno)
        tty.setcbreak(fileno)

    def dataReceived(self, data):
        waiter = self.character_waiter
        self.character_waiter = Deferred()
        waiter.callback(data)

    def connectionLost(self, reason):
        # restore the terminal
        fileno = sys.stdin.fileno()
        termios.tcsetattr(fileno, termios.TCSADRAIN, self.old_termio_settings)

    @inlineCallbacks
    def read_character(self):
        while True:
            character = yield self.character_waiter
            if character:
                returnValue(character)


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
        # don't bother pausing if we're at the end
        completed_hosts = sum(
            1 for result in self.host_results.itervalues()
            if result is not None)
        total_hosts = len(self.host_results)

        if completed_hosts + self.pause_after >= total_hosts:
            return

        self.enqueued_hosts += 1

        if self.pause_after and self.enqueued_hosts == self.pause_after:
            # wait for outstanding hosts to finish up
            yield DeferredList(deploys, consumeErrors=True)

            # prompt the user to continue
            print colorize(
                "*** waiting for input: e[x]it, [c]ontinue, [a]ll remaining, "
                "[1-9] more hosts", Color.BOLD(Color.CYAN))

            while True:
                c = yield self.console_input.read_character()

                if c == "a":
                    self.pause_after = 0
                    break
                elif c == "x":
                    raise AbortDeploy("x pressed")
                elif c == "c":
                    self.pause_after = 1
                    break
                else:
                    try:
                        num_hosts = int(c)
                    except ValueError:
                        continue

                    if num_hosts > 0:
                        self.pause_after = num_hosts
                        break

            self.enqueued_hosts = 0
