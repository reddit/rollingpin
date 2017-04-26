import ConfigParser
import unittest

import rollingpin.config

from tests import make_configparser


class TestMissingData(unittest.TestCase):

    def test_missing_section(self):
        parser = ConfigParser.ConfigParser()
        with self.assertRaises(rollingpin.config.ConfigurationError) as info:
            rollingpin.config.coerce_and_validate_config(parser, {
                "section": {
                    "key": rollingpin.config.Option(str),
                },
            })
        errors = info.exception.errors
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], rollingpin.config.MissingSectionError)

    def test_missing_key(self):
        parser = ConfigParser.ConfigParser()
        parser = make_configparser("""
        [section]
        other = not what we want
        """)
        with self.assertRaises(rollingpin.config.ConfigurationError) as info:
            rollingpin.config.coerce_and_validate_config(parser, {
                "section": {
                    "key": rollingpin.config.Option(str),
                },
            })
        errors = info.exception.errors
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], rollingpin.config.MissingItemError)

    def test_default(self):
        parser = make_configparser("""
        [section]
        """)
        config = rollingpin.config.coerce_and_validate_config(parser, {
            "section": {
                "key": rollingpin.config.Option(int, default=3),
            },
        })
        self.assertEqual(config["section"]["key"], 3)


class TestConfiguration(unittest.TestCase):

    def setUp(self):
        self.parser = make_configparser("""
        [section]
        int = 42
        str = this is a test
        """)
        self.spec = {
            "section": {
                "int": rollingpin.config.Option(int),
                "str": rollingpin.config.Option(str),
            },
        }

    def test_copy_to_output(self):
        config = rollingpin.config.coerce_and_validate_config(self.parser, {
            "section": {
                "str": rollingpin.config.Option(str),
            },
        })
        self.assertEqual({"section": {"str": "this is a test"}}, config)

    def test_values_coerced(self):
        config = rollingpin.config.coerce_and_validate_config(self.parser, {
            "section": {
                "int": rollingpin.config.Option(int),
            },
        })
        self.assertEqual({"section": {"int": 42}}, config)

    def test_failed_coercion(self):
        with self.assertRaises(rollingpin.config.ConfigurationError) as info:
            rollingpin.config.coerce_and_validate_config(self.parser, {
                "section": {
                    "str": rollingpin.config.Option(int),
                },
            })
        errors = info.exception.errors
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], rollingpin.config.CoercionError)


class TestOptionalSections(unittest.TestCase):

    def test_bad_optional_section(self):
        parser = ConfigParser.ConfigParser()
        with self.assertRaises(rollingpin.config.NoDefaultInOptionalSection):
            rollingpin.config.coerce_and_validate_config(parser, {
                "optional-section": rollingpin.config.OptionalSection({
                    "key": rollingpin.config.Option(int),
                })
            })

    def test_optional_section_missing(self):
        parser = ConfigParser.ConfigParser()
        config = rollingpin.config.coerce_and_validate_config(parser, {
            "optional-section": rollingpin.config.OptionalSection({
                "key": rollingpin.config.Option(int, default=3),
            })
        })
        self.assertEqual(config["optional-section"]["key"], 3)

    def test_optional_section_present(self):
        parser = make_configparser("""
        [optional-section]
        key = value
        """)
        config = rollingpin.config.coerce_and_validate_config(parser, {
            "optional-section": rollingpin.config.OptionalSection({
                "key": rollingpin.config.Option(str, default=None),
            })
        })
        self.assertEqual(config["optional-section"]["key"], "value")
