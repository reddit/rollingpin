import json
import logging
import posixpath
import urlparse

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue, CancelledError
from twisted.web.client import Agent, readBody


TIMEOUT_SECONDS = 5


# this is the "safe" response so if we're not configured or something goes
# wrong we'll just not prompt the user so deploys aren't blocked.
SAFE_DEFAULT = {"time_status": "work_time", "busy": False}


@inlineCallbacks
def _do_status_http_request(harold_base_url):
    base_url = urlparse.urlparse(harold_base_url)
    path = posixpath.join(base_url.path, "harold/deploy/status")
    url = urlparse.urlunparse((
        base_url.scheme,
        base_url.netloc,
        path,
        None,
        None,
        None
    ))

    agent = Agent(reactor)
    response = yield agent.request("GET", url)
    if response.code != 200:
        raise Exception("harold responded with an error: %d" % response.code)
    body = yield readBody(response)
    returnValue(json.loads(body))


@inlineCallbacks
def fetch_deploy_status(config):
    harold_base_url = config["harold"]["base-url"]
    if not harold_base_url:
        returnValue(SAFE_DEFAULT)

    fetch_req = _do_status_http_request(harold_base_url)

    # give the request a few seconds and bail out if it takes too long
    timeout = reactor.callLater(TIMEOUT_SECONDS, fetch_req.cancel)

    def cancel_timeout(passthrough):
        if timeout.active():
            timeout.cancel()
        return passthrough
    fetch_req.addBoth(cancel_timeout)

    try:
        result = yield fetch_req
    except CancelledError:
        logging.warning("failed to fetch deploy status: timed out")
        returnValue(SAFE_DEFAULT)
    except Exception as exc:
        logging.warning("failed to fetch deploy status: %s", exc)
        returnValue(SAFE_DEFAULT)

    returnValue(result)
