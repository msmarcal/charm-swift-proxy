import mock
import unittest
import uuid


with mock.patch('charmhelpers.core.hookenv.log'):
    import swift_hooks


class SwiftHooksTestCase(unittest.TestCase):

    def test_all_peers_stopped(self):
        token1 = str(uuid.uuid4())
        token2 = str(uuid.uuid4())
        responses = [{'some-other-key': token1}]
        self.assertFalse(swift_hooks.all_peers_stopped(responses))

        responses = [{'stop-proxy-service-ack': token1},
                     {'stop-proxy-service-ack': token2}]
        self.assertFalse(swift_hooks.all_peers_stopped(responses))

        responses = [{'stop-proxy-service-ack': token1},
                     {'stop-proxy-service-ack': token1}]
        self.assertTrue(swift_hooks.all_peers_stopped(responses))

        responses = [{'stop-proxy-service-ack': token1},
                     {'stop-proxy-service-ack': token1},
                     {'some-other-key': token1}]
        self.assertFalse(swift_hooks.all_peers_stopped(responses))
