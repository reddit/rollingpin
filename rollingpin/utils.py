import os
import random
import re

from twisted.internet import reactor
from twisted.internet.defer import Deferred


def sleep(seconds):
    """Return a Deferred that will fire its callback `seconds` later."""
    deferred = Deferred()
    reactor.callLater(seconds, deferred.callback, seconds)
    return deferred


def random_word(wordlist_path):
    """Return a random word chosen from a given dictionary file."""
    file_size = os.path.getsize(wordlist_path)

    with open(wordlist_path, "r") as wordlist:
        word = ""
        while not word.isalpha() or not word.islower() or len(word) < 5:
            position = random.randint(1, file_size)
            wordlist.seek(position)
            wordlist.readline()
            word = unicode(wordlist.readline().rstrip("\n"), "utf-8")
    return word


def sorted_nicely(iterable):
    """Sort strings with embedded numbers in them the way humans would expect.

    http://nedbatchelder.com/blog/200712/human_sorting.html#comments

    """

    def tryint(maybe_int):
        try:
            return int(maybe_int)
        except ValueError:
            return maybe_int

    def alphanum_key(key):
        return [tryint(c) for c in re.split("([0-9]+)", key)]

    return sorted(iterable, key=alphanum_key)
