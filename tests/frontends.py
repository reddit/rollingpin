import unittest

from rollingpin.deploy import DeployResult
from rollingpin.frontends import generate_component_report
from rollingpin.hostsources import Host


class TestFrontends(unittest.TestCase):

    def test_coverage_report_generation(self):

        # Setup
        host = Host.from_hostname('test')
        results = [
            DeployResult(
                command=['components'],
                result={'components': {'foo': {'abcdef': 1}}},
            ),
        ]
        host_results = {host: {'status': "complete", 'output': results}}

        # Generate Report
        report = generate_component_report(host_results)

        # Verify
        expected_report = {
            'foo': {
                'abcdef': 1,
            },
        }
        self.assertEqual(report, expected_report)

    def test_coverage_report_skips_other_commands(self):

        # Setup
        host = Host.from_hostname('test')
        results = [
            DeployResult(
                command=['deploy', 'foo'],
                result={},
            ),
            DeployResult(
                command=['components'],
                result={'components': {'foo': {'abcdef': 1}}},
            ),
        ]
        host_results = {host: {'status': "complete", 'output': results}}

        # Generate Report
        report = generate_component_report(host_results)

        # Verify
        expected_report = {
            'foo': {
                'abcdef': 1,
            },
        }
        self.assertEqual(report, expected_report)

    def test_coverage_report_doesnt_break_when_no_coverage_report_requested(self):  # noqa

        # Setup
        host = Host.from_hostname('test')
        results = [
            DeployResult(
                command=['deploy', 'foo'],
                result={},
            ),
        ]
        host_results = {host: {'status': "complete", 'output': results}}

        # Generate Report
        report = generate_component_report(host_results)

        # Verify
        self.assertEqual(report, {})

    def test_coverage_report_aggregates_multiple_hosts(self):

        # Setup
        results = [
            DeployResult(
                command=['components'],
                result={'components': {'foo': {'abcdef': 1}}},
            ),
        ]
        host_results = {
            Host.from_hostname('test'): {'status': "complete", 'output': results},
            Host.from_hostname('test-2'): {'status': "complete", 'output': results},
        }

        # Generate Report
        report = generate_component_report(host_results)

        # Verify
        expected_report = {'foo': {'abcdef': 2}}
        self.assertEqual(report, expected_report)
