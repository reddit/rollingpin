import hashlib
import hmac
import json
import logging
import posixpath
import time
import urllib
import urlparse

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, returnValue, CancelledError
from twisted.web.client import Agent, readBody
from twisted.web.http_headers import Headers


TIMEOUT_SECONDS = 5


# this is the "safe" response so if we're not configured or something goes
# wrong we'll just not prompt the user so deploys aren't blocked.
SAFE_DEFAULT = {
    "time_status": "work_time",
    "busy": False,
    "hold": None,
}


@inlineCallbacks
def _do_status_http_request(harold_base_url, harold_secret, salon):
    base_url = urlparse.urlparse(harold_base_url)
    path = posixpath.join(base_url.path, "harold/deploy/status")
    url = urlparse.urlunparse((
        base_url.scheme,
        base_url.netloc,
        path,
        None,
        urllib.urlencode({"salon": salon}),
        None
    ))

    now = str(int(time.time()))
    signature = hmac.new(harold_secret, now, hashlib.sha256).hexdigest()
    signature_header = "%s:%s" % (now, signature)

    agent = Agent(reactor)
    headers = Headers({
        "User-Agent": ["rollingpin"],
        "X-Signature": [signature_header],
    })
    response = yield agent.request("GET", url, headers)
    if response.code != 200:
        raise Exception("harold responded with an error: %d" % response.code)
    body = yield readBody(response)
    returnValue(json.loads(body))


@inlineCallbacks
def fetch_deploy_status(config):
    harold_base_url = config["harold"]["base-url"]
    harold_secret = config["harold"]["hmac-secret"]
    salon = config["harold"]["salon"]
    if not harold_base_url or not harold_secret or not salon:
        returnValue(SAFE_DEFAULT)

    fetch_req = _do_status_http_request(harold_base_url, harold_secret, salon)

    def log_timeout(d, timeout):
        logging.warning("failed to fetch deploy status: timed out")
        return SAFE_DEFAULT

    fetch_req.addTimeout(TIMEOUT_SECONDS, reactor, onTimeoutCancel=log_timeout)

    try:
        result = yield fetch_req
    except Exception as exc:
        logging.warning("failed to fetch deploy status: %s", exc)
        returnValue(SAFE_DEFAULT)

    returnValue(result)
