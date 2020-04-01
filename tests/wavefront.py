import json
import unittest
from mock import MagicMock, patch

from rollingpin.wavefront import WavefrontNotifier


@patch('time.time', MagicMock(return_value=1))
class TestWavefrontNotifier(unittest.TestCase):

    def setUp(self):
        self.components = ["service-1", "service-2"]
        self.hosts = ["host1", "host2", "host3"]
        self.command = "somerolloutcommand"
        self.deploy_word = "fat-rabbit"
        self.config = {
            "wavefront": {
                "endpoint": "https://test.wavefront.com",
                "api_key": "testkey"
            }
        }
        self.profile = "example-profile"
        self.wf_notifier_args = [
            self.config,
            self.components,
            self.hosts,
            self.command,
            self.deploy_word,
            self.profile,
        ]
        self.wf_notifier = WavefrontNotifier(*self.wf_notifier_args)

    @patch('rollingpin.wavefront.reactor', MagicMock())
    def test_open_event(self):
        agent = MagicMock()
        event = {'hello': 'world'}
        patch_target = 'rollingpin.wavefront.Agent'
        with patch(patch_target, MagicMock(return_value=agent)):
            self.wf_notifier.open_deploy_event(event)

        agent.request.assert_called()
        args = agent.request.call_args[0]
        self.assertEquals(len(args), 4)
        method, endpoint, headers, body = args
        self.assertEquals(method, 'POST')
        self.assertEquals(endpoint, 'https://test.wavefront.com/api/v2/event')
        header_list = [{key: value}
                       for key, value in headers.getAllRawHeaders()]
        self.assertEquals(
            header_list,
            [
                {'Content-Type': ['application/JSON']},
                {'Authorization': ['Bearer testkey']},
            ]
        )
        self.assertEquals(body.getBody(), json.dumps(event))

    def test_deploy_abort_event(self):
        reason = "testabort"
        deploy_abort_event = self.wf_notifier.deploy_abort_event(reason)
        expected_deploy_abort_event = {
            'annotations': {
                'details': 'deploy-name=fat-rabbit',
                'severity': 'warn',
                'type': 'Rollingpin Deploy'
            },
            'endTime': 1000,
            'name': 'example-profile Deploy',
            'tags': ['example-profile.deploy', 'deploy', 'example-profile.deploy.aborted'],
        }
        self.assertEquals(deploy_abort_event, expected_deploy_abort_event)

    def test_deploy_end_event(self):
        deploy_end_event = self.wf_notifier.deploy_end_event()
        expected_deploy_end_event = {
            'annotations': {
                'details': 'deploy-name=fat-rabbit',
                'severity': 'info',
                'type': 'Rollingpin Deploy'
            },
            'endTime': 1000,
            'name': 'example-profile Deploy',
            'tags': ['example-profile.deploy', 'deploy']
        }
        self.assertEquals(deploy_end_event, expected_deploy_end_event)
