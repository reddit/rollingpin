import collections
import contextlib
import math
import re

from twisted.internet import reactor
from twisted.internet.defer import (
    Deferred,
    DeferredSemaphore,
    gatherResults,
    inlineCallbacks,
    returnValue,
)


MAX_PARALLELISM = 50


@contextlib.contextmanager
def swallow_exceptions(title, log):
    """Decorator to swallow exception. Used in conjuction with
    a 'with' statement"""
    try:
        yield
    except Exception as e:
        log.warning("%s: %s", title, e)


def sleep(seconds):
    """Return a Deferred that will fire its callback `seconds` later."""
    deferred = Deferred()
    reactor.callLater(seconds, deferred.callback, seconds)
    return deferred


valid_push_word = re.compile("^[a-z:]{5,}$")


@inlineCallbacks
def parallel_map(iterable, fn, *args, **kwargs):
    deferreds = []
    parallelism_limiter = DeferredSemaphore(MAX_PARALLELISM)
    for item in iterable:
        d = parallelism_limiter.run(fn, item, *args, **kwargs)
        deferreds.append(d)
    results = yield gatherResults(deferreds)
    returnValue(results)


def _distribute_into(master, additions):
    assert len(master) >= len(additions)

    spread = int(math.ceil(float(len(master)) / len(additions)))

    for i, item in enumerate(additions):
        master.insert(i * spread, item)


def interleaved(items, key):
    """Reorder a list such that items of the same key are maximally apart.

    This ensures that no pool gets a bunch of its servers taken down all at
    the same time due to an unlucky host ordering.

    """
    if not items:
        return []

    grouped = collections.defaultdict(list)
    for item in items:
        grouped[key(item)].append(item)

    groups_by_size = sorted(grouped.values(), key=len, reverse=True)

    result = groups_by_size[0]
    for items in groups_by_size[1:]:
        _distribute_into(result, items)
    return result


# https://stackoverflow.com/a/1181922
def b36encode(number, alphabet='0123456789abcdefghijklmnopqrstuvwxyz'):
    """Convert an integer to a base36 string."""
    if not isinstance(number, (int, long)):
        raise TypeError('number must be an integer')

    base36 = ''
    sign = ''

    if number < 0:
        sign = '-'
        number = -number

    if 0 <= number < len(alphabet):
        return sign + alphabet[number]

    while number != 0:
        number, i = divmod(number, len(alphabet))
        base36 = alphabet[i] + base36

    return sign + base36
