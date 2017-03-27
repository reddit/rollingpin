import unittest

from rollingpin.deploy import Deployer


class TestDeployer(unittest.TestCase):
    def test_constructor(self):
        config = {
            'hostsource': 'hostsrc',
            'transport': object(),
            'deploy': {
                'code-host': object()
            }
        }
        event_bus = object()
        deployer = Deployer(config, event_bus,
                            parallel=10,
                            timeout=11,
                            sleeptime=12,
                            dangerously_fast=True
                            )
        self.assertEquals(deployer.code_host, config['deploy']['code-host'])
        self.assertEquals(deployer.host_source, 'hostsrc')
        self.assertEquals(deployer.transport, config['transport'])
        self.assertEquals(deployer.event_bus, event_bus)
        self.assertEquals(deployer.parallel, 10)
        self.assertEquals(deployer.execution_timeout, 11)
        self.assertEquals(deployer.sleeptime, 12)
        self.assertEquals(deployer.dangerously_fast, True)
