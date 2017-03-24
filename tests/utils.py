import unittest

import logging
from mock import Mock

from rollingpin.utils import swallow_exceptions


class TestUtils(unittest.TestCase):

    def test_swallow_exception_on_error(self):
        logger = Mock()
        exception = Exception("fail")
        with swallow_exceptions("tester", logger):
            raise exception
        logger.warning.assert_called_with('%s: %s', 'tester', exception)

    def test_swallow_exception_no_error(self):
        logger = Mock()
        with swallow_exceptions("tester", logger):
            pass
        logger.warning.assert_not_called()
