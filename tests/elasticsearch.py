import json
import unittest
from mock import MagicMock, patch

from rollingpin.elasticsearch import ElasticSearchNotifier


@patch('time.time', MagicMock(return_value=1))
class TestElasticSearchNotifier(unittest.TestCase):

    def setUp(self):
        self.components = ["service-1", "service-2"]
        self.hosts = ["host1", "host2", "host3"]
        self.command = "somerolloutcommand"
        self.deploy_word = "fat-rabbit"
        self.config = {
            "elasticsearch": {
                "endpoint": "metric.com:123",
                "index": "myindex",
                "type": "mytype"
            }
        }
        self.profile = "example-profile"
        self.es_notifier_args = [
            self.config,
            self.components,
            self.hosts,
            self.command,
            self.deploy_word,
            self.profile,
        ]
        self.es_notifier = ElasticSearchNotifier(*self.es_notifier_args)

    @patch('rollingpin.elasticsearch.reactor', MagicMock())
    def test_index_doc(self):
        agent = MagicMock()
        doc = {'hello': 'world'}
        patch_target = 'rollingpin.elasticsearch.Agent'
        with patch(patch_target, MagicMock(return_value=agent)):
            self.es_notifier.index_doc(doc)

        agent.request.assert_called()
        args = agent.request.call_args[0]
        self.assertEquals(len(args), 4)
        method, endpoint, headers, body = args
        self.assertEquals(method, 'POST')
        self.assertEquals(endpoint, 'https://metric.com:123/myindex/mytype')
        header_list = [{key: value}
                       for key, value in headers.getAllRawHeaders()]
        self.assertEquals(header_list, [{'User-Agent': ['rollingpin']}])
        self.assertEquals(body.getBody(), json.dumps(doc))

    def test_build_sync_doc(self):
        sync_info = {
            'foo': {'token': 'aaaaaaa'},
            'bar': {'token': 'bbbbbbb'},
        }
        build_sync_doc = self.es_notifier.build_sync_doc(sync_info)
        expected_build_sync_doc = {
            'sync_targets': 'foo@aaaaaaa, bar@bbbbbbb',
        }
        self.assertEquals(build_sync_doc, expected_build_sync_doc)

    def test_deploy_start_doc(self):
        deployer = "mr_cool_guy"
        with patch('getpass.getuser', MagicMock(return_value=deployer)):
            deploy_start_doc = self.es_notifier.deploy_start_doc()
        expected_deploy_start_doc = {
            'host_count': len(self.hosts),
            'hosts': self.hosts,
            'command': self.command,
            'event_type': 'deploy.begin',
            'components': self.components,
            'deployer': deployer,
            'timestamp': 1000,
            'id': self.deploy_word,
            'profile': 'example-profile',
        }
        self.assertEquals(deploy_start_doc, expected_deploy_start_doc)

    def test_deploy_abort_doc(self):
        reason = "farrabbitssss"
        deploy_abort_doc = self.es_notifier.deploy_abort_doc(reason)
        expected_deploy_abort_doc = {
            'timestamp': 1000,
            'reason': 'farrabbitssss',
            'components': self.components,
            'id': self.deploy_word,
            'event_type': 'deploy.abort',
            'profile': 'example-profile',
        }
        self.assertEquals(deploy_abort_doc, expected_deploy_abort_doc)

    def test_deploy_end_doc(self):
        deploy_end_doc = self.es_notifier.deploy_end_doc()
        expected_deploy_end_doc = {
            'timestamp': 1000,
            'components': self.components,
            'id': self.deploy_word,
            'event_type': 'deploy.end',
            'profile': 'example-profile',
        }
        self.assertEquals(deploy_end_doc, expected_deploy_end_doc)
