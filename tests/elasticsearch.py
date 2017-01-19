import unittest
from mock import MagicMock, patch
from twisted.web.http_headers import Headers
from rollingpin.elasticsearch import ElasticSearchNotifier


class TestElasticSearchNotifier(unittest.TestCase):

    def setUp(self):
        self.components = ["service-1", "service-2"]

    @patch('time.time', MagicMock(return_value=1))
    def test_bulk_updates(self):
        bulk_updates = ElasticSearchNotifier.bulk_updates(self.components)
        self.assertEquals([
            '{"index": {}}',
            '{"timestamp": 1, "service": "service-1"}',
            '{"index": {}}',
            '{"timestamp": 1, "service": "service-2"}',
        ], bulk_updates)

    def test_request_body(self):
        bulk_updates = MagicMock(return_value=["1", "2", "3"])
        patch_target = 'rollingpin.elasticsearch.ElasticSearchNotifier.bulk_updates'  # noqa
        with patch(patch_target, bulk_updates):
            body = ElasticSearchNotifier.request_body(self.components)
            self.assertEquals(body, "1\n2\n3\n")

    @patch('rollingpin.elasticsearch.reactor', MagicMock())
    @patch('time.time', MagicMock(return_value=1))
    def test_on_deploy_start(self):
        components = ["service-1", "service-2"]
        config = {
            "elasticsearch": {
                "endpoint": "metric.com:123",
                "index": "myindex",
                "type": "mytype"
            }
        }
        agent = MagicMock()
        agent_module = MagicMock(return_value=agent)
        with patch('rollingpin.elasticsearch.Agent', agent_module):
            notifier = ElasticSearchNotifier(config, components)
            notifier.on_deploy_start()
        agent.request.assert_called()
        args = agent.request.call_args[0]
        self.assertEquals(len(args), 4)
        method, endpoint, headers, body_producer = args
        self.assertEquals(method, 'POST')
        self.assertEquals(endpoint, 'https://metric.com:123/myindex/mytype/_bulk')
        header_list = [{key: value}
                       for key, value in headers.getAllRawHeaders()]
        self.assertEquals(header_list, [{'User-Agent': ['rollingpin']}])
        expected_body = ('{"index": {}}\n'
                         '{"timestamp": 1, "service": "service-1"}\n'
                         '{"index": {}}\n'
                         '{"timestamp": 1, "service": "service-2"}\n')
        self.assertEquals(expected_body, body_producer.getBody())
