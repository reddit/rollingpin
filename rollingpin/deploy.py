import collections
import logging
import signal
import traceback

from twisted.internet import reactor
from twisted.internet.defer import (
    DeferredList,
    DeferredSemaphore,
    inlineCallbacks,
    returnValue,
)

from .hostsources import Host
from .transports import TransportError, ExecutionTimeout
from .utils import sleep


SIGNAL_MESSAGES = {
    signal.SIGINT: "received SIGINT",
    signal.SIGHUP: "received SIGHUP. tsk tsk.",
}


class AbortDeploy(Exception):
    pass


class DeployError(Exception):
    pass


class HostDeployError(DeployError):

    def __init__(self, host, error):
        self.host = host
        self.error = error
        super(HostDeployError, self).__init__()

    def __str__(self):
        return "{}: {}".format(self.host, self.error)


class ComponentNotBuiltError(DeployError):

    def __init__(self, component):
        self.component = component
        super(ComponentNotBuiltError, self).__init__()

    def __str__(self):
        return "{}: build token not generated".format(self.component)


DeployResult = collections.namedtuple('DeployResult', ['command', 'result'])


class Deployer(object):

    def __init__(self, config, event_bus, parallel,
                 sleeptime, timeout, dangerously_fast):
        """
        :param dict config:
        :param EventBus event_bus:
        :param int parallel: number of hosts to process in parallel
        :param float sleeptime: sleep time between hosts
        :param int timeout: command execution timeout
        :param bool dangerously_fast: flag to ignore wait for reloads

        """
        self.log = logging.getLogger(__name__)
        self.host_source = config["hostsource"]
        self.transport = config["transport"]
        self.event_bus = event_bus
        self.parallel = parallel
        self.code_host = config["deploy"]["code-host"]
        self.execution_timeout = timeout
        self.sleeptime = sleeptime
        self.dangerously_fast = dangerously_fast

    @inlineCallbacks
    def process_host(self, host, commands, timeout=0):
        log = logging.LoggerAdapter(self.log, {"host": host.name})

        yield self.event_bus.trigger("host.begin", host=host)

        results = []

        try:
            log.info("connecting")
            connection = yield self.transport.connect_to(host.address)
            for command in commands:
                log.info(" ".join(command))
                yield self.event_bus.trigger(
                    "host.command", host=host, command=command)
                result = yield connection.execute(log, command, timeout)
                results.append(DeployResult(command, result))
            yield connection.disconnect()
        except TransportError as e:
            should_be_alive = yield self.host_source.should_be_alive(host)
            if should_be_alive:
                log.error("error: %s", e)
            else:
                log.warning("error on possibly terminated host: %s", e)

            yield self.event_bus.trigger(
                "host.abort", host=host, error=e,
                should_be_alive=should_be_alive)
            raise HostDeployError(host, e)
        else:
            log.info("success! all done")
            yield self.event_bus.trigger(
                "host.end", host=host, results=results)

        returnValue(results)

    @inlineCallbacks
    def on_host_error(self, reason):
        if not reason.check(DeployError):
            reason.printTraceback()
            yield self.abort(reason.getErrorMessage())

    @inlineCallbacks
    def run_deploy(self, hosts, components, commands):
        try:
            yield self.event_bus.trigger("deploy.precheck")
        except AbortDeploy as e:
            yield self.abort(str(e))
            return

        try:
            self.transport.initialize()
        except TransportError as e:
            raise DeployError("could not initialize transport: %s" % e)

        def signal_handler(sig, _):
            reason = SIGNAL_MESSAGES[sig]
            reactor.callFromThread(self.abort, reason)
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGHUP, signal_handler)

        yield self.event_bus.trigger("deploy.begin")

        try:
            if components:
                yield self.event_bus.trigger("build.begin")

                try:
                    # synchronize the code host with upstreams
                    # this will return a build token and build host for each
                    # component
                    sync_command = ["synchronize"] + components
                    code_host = Host.from_hostname(self.code_host)
                    (sync_result,) = yield self.process_host(
                        code_host, [sync_command])
                    yield self.event_bus.trigger("build.sync",
                                                 sync_info=sync_result.result)

                    # this is where we build up the final deploy command
                    # resulting from all our syncing and building
                    deploy_command = ["deploy"]

                    # collect the results of the sync per-buildhost
                    by_buildhost = collections.defaultdict(list)
                    for component, sync_info in sync_result.result.iteritems():
                        component_ref = component + "@" + sync_info["token"]

                        build_host = sync_info.get("buildhost", None)
                        if build_host:
                            by_buildhost[build_host].append(component_ref)
                        else:
                            # no build host means we just pass the sync token
                            # straight through as a deploy token
                            deploy_command.append(component_ref)

                    # ask each build host to build our components and return
                    # a deploy token
                    for build_hostname, build_refs in by_buildhost.iteritems():
                        build_command = ["build"] + build_refs
                        build_host = Host.from_hostname(build_hostname)
                        (build_result,) = yield self.process_host(
                            build_host, [build_command])

                        for ref in build_refs:
                            component, at, sync_token = ref.partition("@")
                            assert at == "@"
                            try:
                                deploy_ref = (component + "@" +
                                              build_result.result[ref])
                            except KeyError:
                                raise ComponentNotBuiltError(component)
                            deploy_command.append(deploy_ref)

                    # Wait until components report ready IF:
                    # * we are actually restarting a component
                    # * we aren't going --dangerously-fast
                    restarting_component = any(
                        ["restart" in val for val in commands])
                    if restarting_component and not self.dangerously_fast:
                        commands.append(["wait-until-components-ready"])
                except Exception:
                    traceback.print_exc()
                    raise DeployError("unexpected error in sync/build")
                else:
                    # inject our built-up deploy command at the beginning of
                    # the command list for each host
                    commands = [deploy_command] + commands

                yield self.event_bus.trigger("build.end")

            parallelism_limiter = DeferredSemaphore(tokens=self.parallel)
            host_deploys = []
            first_host = True
            for host in hosts:
                if not first_host:
                    for i in xrange(self.sleeptime, 0, -1):
                        yield self.event_bus.trigger(
                            "deploy.sleep", host=host, count=i)
                        yield sleep(1)
                else:
                    first_host = False

                deferred = parallelism_limiter.run(
                    self.process_host, host, commands,
                    timeout=self.execution_timeout)
                deferred.addErrback(self.on_host_error)
                host_deploys.append(deferred)

                yield self.event_bus.trigger(
                    "deploy.enqueue", host=host, deferred=deferred)
            yield DeferredList(host_deploys)
        except (DeployError, AbortDeploy, TransportError) as e:
            yield self.abort(str(e))
        else:
            yield self.event_bus.trigger("deploy.end")

    @inlineCallbacks
    def abort(self, reason):
        yield self.event_bus.trigger("deploy.abort", reason=reason)
        reactor.stop()
