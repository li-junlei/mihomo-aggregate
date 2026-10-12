import base64
import os
import unittest
from unittest.mock import Mock, patch

with patch.dict(os.environ, {'ADMIN_PASSWORD': 'test-password-at-least-16'}):
    import panel


class AuthTests(unittest.TestCase):
    def handler(self, authorization=''):
        handler = object.__new__(panel.Handler)
        handler.headers = {'Authorization': authorization}
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        return handler

    def test_no_login_when_enabled(self):
        with patch.object(panel, 'AUTH_DISABLED', True):
            handler = self.handler()
            self.assertTrue(handler.auth())
            handler.send_response.assert_not_called()

    def test_password_required_by_default(self):
        with patch.object(panel, 'AUTH_DISABLED', False):
            handler = self.handler()
            self.assertFalse(handler.auth())
            handler.send_response.assert_called_once_with(401)
            credentials = base64.b64encode(('admin:' + panel.PASSWORD).encode()).decode()
            self.assertTrue(self.handler('Basic ' + credentials).auth())
            self.assertFalse(self.handler('Basic invalid').auth())


if __name__ == '__main__':
    unittest.main()
