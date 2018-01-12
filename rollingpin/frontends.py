from __future__ import division

import collections
import logging
import math
import re
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
from .status import fetch_deploy_status


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


def generate_component_report(host_results):
    """Aggregate a list of results from the `components` deploy command."""
    report = collections.defaultdict(collections.Counter)
    for host, results in host_results.iteritems():
        for result in results.get('output', []):
            if result.command[0] != 'components':
                continue
            # Example result.result['components']:
            #
            #     {
            #         'foo': {
            #             'abcdef': 2,
            #         },
            #     }
            for component, sha_counts in result.result['components'].iteritems():
                for sha, count in sha_counts.iteritems():
                    report[component][sha] += count
    return report


def calculate_percent_complete(hosts):
    completed = sum(1 for state in hosts.itervalues()
                    if state["status"] == "complete")
    return int((completed / len(hosts)) * 100)


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

        self.hosts = {host: {"status": "pending"} for host in hosts}
        self.start_time = None

        event_bus.register({
            "deploy.begin": self.on_deploy_begin,
            "deploy.end": self.on_deploy_end,
            "deploy.abort": self.on_deploy_abort,
            "deploy.enqueue": self.on_enqueue,
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

    @inlineCallbacks
    def on_enqueue(self, host, deferred):
        # this is to trick python into thinking this is a generator so it
        # works properly with @inlineCallbacks
        if False:
            yield

        self.hosts[host]["status"] = "deploying"
        self.hosts[host]["deferred"] = deferred

    def on_host_end(self, host, results):
        if host in self.hosts:
            self.hosts[host]["status"] = "complete"
            self.hosts[host]["result"] = "success"
            self.hosts[host]["output"] = results
            try:
                del self.hosts[host]["deferred"]
            except KeyError:
                pass
            self._print_percent_complete()

    def on_host_abort(self, host, error, should_be_alive):
        if host in self.hosts:
            self.hosts[host]["status"] = "complete"
            self.hosts[host]["result"] = "aborted"
            self.hosts[host]["should_be_alive"] = should_be_alive
            try:
                del self.hosts[host]["deferred"]
            except KeyError:
                pass
            self._print_percent_complete()

    def _print_percent_complete(self):
        percent_complete = calculate_percent_complete(self.hosts)
        print colorize("*** %d%% done" % percent_complete, Color.GREEN)

    def on_deploy_abort(self, reason):
        print colorize(
            "*** deploy aborted: %s" % reason, Color.BOLD(Color.RED))

    def on_deploy_end(self):
        print colorize("*** deploy complete!", Color.BOLD(Color.GREEN))
        elapsed = time.time() - self.start_time
        print "*** elapsed time: %d seconds" % elapsed

        report = generate_component_report(self.hosts)
        if report:
            # Pad the columns to reasonable max widths so the tabs will line up
            # and be readable.  For SHAs, we expect 40 characters.  For
            # components and counts, we choose some reasonably large lengths
            # that we may need to adjust later.
            fmt_string = "%20s\t%40s\t%10s"
            print colorize("*** component report", Color.BOLD(Color.GREEN))
            print fmt_string % ("COMPONENT", "SHA", "COUNT")
            for component in report.keys():
                for sha, count in report[component].iteritems():
                    print fmt_string % (component, sha, count)


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


OPTION_RE = re.compile(r"^[^[]*\[([a-z])\][^\]]*$")


@inlineCallbacks
def prompt_choice(console_input, options):
    assert len(options) >= 2

    print

    letters = []
    for option in options:
        m = OPTION_RE.match(option)
        assert m, "option %r is not validly formatted!!!" % (option)
        letter = m.group(1)
        assert letter not in letters, "two options can't have the same letter!"
        letters.append(letter)

        print ("* " + option[:m.start(1)] +
               colorize(letter, Color.BOLD(Color.CYAN)) +
               option[m.end(1):])

    print
    colorized = [colorize(letter, Color.BOLD(Color.CYAN)) for letter in letters]
    print "Press " + ", ".join(colorized[:-1]) + ", or " + colorized[-1] + "."

    while True:
        character = yield console_input.read_character()
        if character in letters:
            returnValue(character)


@inlineCallbacks
def prompt_declaration(console_input, required_declaration):
    print
    print 'To continue, type "%s" at the prompt or press Ctrl+C to abort.' % required_declaration
    print
    while True:
        entered_declaration = yield console_input.raw_input("> ")
        if entered_declaration.lower() == required_declaration.lower():
            returnValue(None)


class DeployStrategy(object):
    def is_complete(self, hosts):
        raise NotImplementedError

    def get_next_strategy(self, hosts):
        raise NotImplementedError


class FirstHostDeployStrategy(DeployStrategy):
    """Deploy to the first host in the list and pause."""

    def __init__(self, console_input):
        self.console_input = console_input

    def is_complete(self, hosts):
        return True

    @inlineCallbacks
    def get_next_strategy(self, hosts):
        print "Deploy to first host complete, what should I do now?"
        selection = yield prompt_choice(self.console_input, (
            "something's wrong, [a]bort the deploy!",
            "that host isn't spewing errors, [c]ontinue to all canaries",
        ))

        if selection == "a":
            raise AbortDeploy("user aborted deploy")
        elif selection == "c":
            returnValue(CanaryDeployStrategy(self.console_input))


class CanaryDeployStrategy(DeployStrategy):
    """Deploy to at least one host in each pool before pausing."""

    def __init__(self, console_input):
        self.console_input = console_input
        self.enqueued_pools = set()

    def is_complete(self, hosts):
        all_pools = {host.pool for host in hosts.iterkeys()}
        pools_deployed_to = {host.pool for host, status in hosts.iteritems()
                             if status["status"] in ("complete", "deploying")}
        untouched_pools = all_pools - pools_deployed_to
        return not untouched_pools

    @inlineCallbacks
    def get_next_strategy(self, hosts):
        pools_deployed_to = {host.pool for host, status in hosts.iteritems()
                             if status["status"] == "complete"}
        if len(pools_deployed_to) > 1:
            print ("Canary deploy complete, please verify the canary "
                   "hosts are not reporting errors in the logs.")
            yield prompt_declaration(self.console_input, "The canaries are healthy")
        else:
            print ("Canary deploy complete, please verify the canary "
                   "host is not reporting errors in the logs.")
            yield prompt_declaration(self.console_input, "The canary is healthy")

        print
        print "Great!"

        next_strategy = yield get_next_regular_strategy(self.console_input, hosts)
        returnValue(next_strategy)


def round_to_next_target(hosts, raw_target):
    """Round up from a target percentage to the next achievable value.

    When the number of hosts is low, there's a minimum jump in percentage
    from host-to-host. This rounds up to the next value so that the user isn't
    surprised by the deploy going further than expected from the prompts.

    """
    minimum_step_size = 1. / len(hosts) * 100
    return int(math.ceil(raw_target / minimum_step_size) * minimum_step_size)


@inlineCallbacks
def get_next_regular_strategy(console_input, hosts):
    options = [
        "something's wrong, [a]bort the deploy!",
    ]
    strategies = {}

    if len(hosts) <= 3:
        options.append("roll out to the [n]ext host")
        strategies["n"] = SingleHostDeployStrategy(console_input)
    else:
        percent_complete = calculate_percent_complete(hosts)

        if percent_complete < 65:
            target = round_to_next_target(hosts, percent_complete + 25)
            options.append("i'm not worried about load, [j]ump forward to %d%% of hosts" % target)
            strategies["j"] = PercentDeployStrategy(console_input, target)

        if percent_complete < 85:
            target = round_to_next_target(hosts, percent_complete + 10)
            options.append("let's keep an eye on load, [s]tep forward to %d%% of hosts" % target)
            strategies["s"] = PercentDeployStrategy(console_input, target)

        if percent_complete >= 65:
            options.append("all is good, [f]inish deploying to 100% of hosts")
            strategies["f"] = FreeDeployStrategy()

    print
    print "What should I do now?"
    selection = yield prompt_choice(console_input, options)

    if selection == "a":
        raise AbortDeploy("user aborted deploy")
    returnValue(strategies[selection])


class SingleHostDeployStrategy(DeployStrategy):
    """Deploy to just one host (but not the first), useful for small batches."""

    def __init__(self, console_input):
        self.console_input = console_input

    def is_complete(self, hosts):
        return True

    @inlineCallbacks
    def get_next_strategy(self, hosts):
        next_strategy = yield get_next_regular_strategy(self.console_input, hosts)
        returnValue(next_strategy)


class PercentDeployStrategy(DeployStrategy):
    """Deploy to a percentage of the total number of hosts."""

    def __init__(self, console_input, target_percent):
        self.console_input = console_input
        self.target_percent = target_percent

    def is_complete(self, hosts):
        completed = sum(1 for state in hosts.itervalues()
                        if state["status"] in ("complete", "deploying"))
        percent_done_or_in_flight = int((completed / len(hosts)) * 100)
        return percent_done_or_in_flight >= self.target_percent

    @inlineCallbacks
    def get_next_strategy(self, hosts):
        next_strategy = yield get_next_regular_strategy(self.console_input, hosts)
        returnValue(next_strategy)


class FreeDeployStrategy(DeployStrategy):
    def is_complete(self, hosts):
        return False

    @inlineCallbacks
    def get_next_strategy(self, hosts):
        raise NotImplementedError


class HeadfulFrontend(HeadlessFrontend):

    def __init__(self, event_bus, hosts, verbose_logging, config):
        HeadlessFrontend.__init__(self, event_bus, hosts, verbose_logging)

        self.console_input = StdioListener()
        StandardIO(self.console_input)

        event_bus.register({
            "deploy.precheck": self.on_precheck,
            "deploy.sleep": self.on_sleep,
        })

        self.config = config

        pools = set(host.pool for host in hosts)
        if len(pools) > 1:
            self.deploy_strategy = FirstHostDeployStrategy(self.console_input)
        else:
            self.deploy_strategy = CanaryDeployStrategy(self.console_input)

    def on_sleep(self, host, count):
        print colorize("*** sleeping %d..." % count, Color.BOLD(Color.BLUE))

    @inlineCallbacks
    def on_precheck(self):
        status = yield fetch_deploy_status(self.config)

        bad_time = status["time_status"] not in ("work_time", "cleanup_time")
        deploy_in_progress = status["busy"]
        hold_reason = status.get("hold")

        if bad_time or deploy_in_progress or hold_reason:
            print colorize("*** WARNING ***", Color.BOLD(Color.RED))

            reasons = []
            if bad_time:
                reasons.append("it is currently outside of normal deploy hours")
            if deploy_in_progress:
                reasons.append("another deploy is currently happening")
            if hold_reason:
                reasons.append("deploys are on hold: " + hold_reason)

            print "This may not be a good time to do a deploy:",
            print ", and ".join(colorize(r, Color.BOLD(Color.YELLOW)) for r in reasons) + ".",
            print

            choice = yield prompt_choice(self.console_input, (
                "whoops! never mind, [a]bort",
                "i have manager approval, [d]eploy anyway",
            ))

            if choice == "a":
                raise AbortDeploy("aborted at precheck")
            elif choice == "d":
                return

    @inlineCallbacks
    def on_enqueue(self, host, deferred):
        yield super(HeadfulFrontend, self).on_enqueue(host, deferred)

        if not any(state["status"] == "pending" for state in self.hosts.itervalues()):
            # there's no reason to pause if all hosts are already in flight
            return

        if self.deploy_strategy.is_complete(self.hosts):
            deferreds = [state["deferred"] for state in self.hosts.itervalues()
                         if state["status"] == "deploying"]
            yield DeferredList(deferreds, consumeErrors=True)

            self.deploy_strategy = yield self.deploy_strategy.get_next_strategy(
                self.hosts)
