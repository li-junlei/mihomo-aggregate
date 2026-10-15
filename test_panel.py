import base64
import os
import io
import json
import tempfile
from pathlib import Path
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

    def test_icon_requires_authentication_when_enabled(self):
        with patch.object(panel, 'AUTH_DISABLED', False):
            handler=self.handler()
            handler.path='/assets/icon-c-crystal.png'
            handler.respond=Mock()
            handler.do_GET()
            handler.send_response.assert_called_once_with(401)
            handler.respond.assert_not_called()


class ApiTests(unittest.TestCase):
    def test_rule_switches_persist_without_refetch(self):
        _, current = self.request('/api/config')
        current['config']['exclude_unhealthy'] = True
        current['config']['exclude_rules'] = [{'name_contains': 'test', 'enabled': False}]
        code, _ = self.request('/api/config', current)
        self.assertEqual(code, 200)
        saved = panel.worker.load_config()
        self.assertTrue(saved['exclude_unhealthy'])
        self.assertFalse(saved['exclude_rules'][0]['enabled'])
        self.assertTrue(panel.worker.read_json(panel.worker.STATE / 'refresh.request', {})['publish_only'])

    def test_reorder_persists_without_fetching_sources(self):
        _, current = self.request('/api/config')
        expected = list(reversed(current['config']['sources']))
        current['config']['sources'] = expected
        code, _ = self.request('/api/config', current)
        self.assertEqual(code, 200)
        self.assertEqual(panel.worker.load_config()['sources'], expected)
        self.assertTrue(panel.worker.read_json(panel.worker.STATE / 'refresh.request', {})['publish_only'])

    def setUp(self):
        import yaml
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('TEST_TMP'))
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.cfg = yaml.safe_load(Path('config/sources.example.yaml').read_text('utf-8'))
        self.config = root / 'sources.yaml'
        self.config.write_text(yaml.safe_dump(self.cfg), encoding='utf-8')
        for name, value in [('CONFIG', self.config), ('STATE', root / 'state')]:
            patcher = patch.object(panel.worker, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(panel, 'AUTH_DISABLED', True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def request(self, path, data=None, headers=None):
        handler = object.__new__(panel.Handler)
        handler.path = path
        handler.respond = Mock()
        body = json.dumps(data).encode()
        handler.rfile = io.BytesIO(body)
        handler.headers = {'Content-Length': str(len(body)), 'X-Panel-Request': '1', **(headers or {})}
        if data is None:
            handler.do_GET()
        else:
            handler.do_POST()
        code, body = handler.respond.call_args.args[:2]
        return code, json.loads(body)

    def test_brand_icon_serves_only_selected_asset(self):
        handler=object.__new__(panel.Handler)
        handler.path='/assets/icon-c-crystal.png'
        handler.headers={}
        handler.respond=Mock()
        handler.do_GET()
        code,body,kind=handler.respond.call_args.args
        self.assertEqual(code,200)
        self.assertTrue(body.startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertEqual(kind,'image/png')
        for path in ('/assets/../.env','/assets/icon-a-ribbon.png'):
            self.assertEqual(self.request(path)[0],404)

    def test_country_choices_only_include_enabled_cached_regions(self):
        import yaml
        self.cfg['sources'][0]['enabled']=True
        self.cfg['sources'][1]['enabled']=False
        self.cfg['country_groups']=['🇺🇸 美国']
        self.config.write_text(yaml.safe_dump(self.cfg),encoding='utf-8')
        code,data=self.request('/api/config')
        self.assertEqual(data['countries'],[])
        for source,name in zip(self.cfg['sources'],('香港','Japan')):
            panel.worker.atomic(panel.worker.STATE/(source['id']+'.json'),json.dumps({'nodes':[{'name':name,'type':'ss','server':'host','port':443}]}))
        _,data=self.request('/api/config')
        self.assertEqual(data['countries'],['🇭🇰 香港'])
        self.assertEqual(data['config']['country_groups'],['🇺🇸 美国'])

    def test_combined_rule_save_uses_cached_publication(self):
        _,data=self.request('/api/config')
        data['config']['exclude_rules']=[{'source_id':self.cfg['sources'][0]['id'],'country':'🇯🇵 日本'},
                                         {'country':'🇬🇧 英国','protocol':'vless'}]
        code,_=self.request('/api/config',data)
        self.assertEqual(code,200)
        self.assertEqual(panel.worker.load_config()['exclude_rules'],data['config']['exclude_rules'])
        self.assertTrue(panel.worker.read_json(panel.worker.STATE/'refresh.request',{})['publish_only'])

    def test_config_version_prevents_lost_updates(self):
        code, old = self.request('/api/config')
        self.assertEqual(code, 200)
        changed = dict(old['config'], health_interval=120)
        code, saved = self.request('/api/config', {'config': changed, 'version': old['version']})
        self.assertEqual(code, 200)
        self.assertNotEqual(saved['version'], old['version'])
        request = (panel.worker.STATE / 'refresh.request').read_bytes()
        self.assertTrue(json.loads(request)['publish_only'])
        before = self.config.read_bytes()
        code, _ = self.request('/api/config', {'config': old['config'], 'version': old['version']})
        self.assertEqual(code, 409)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual((panel.worker.STATE / 'refresh.request').read_bytes(), request)
        code, current = self.request('/api/config')
        self.assertEqual(current['config']['health_interval'], 120)
        self.assertEqual(current['version'], saved['version'])
        code, _ = self.request('/api/config', {'config': current['config'], 'version': current['version']})
        self.assertEqual(code, 200)

    def test_write_origin_protection_even_without_auth(self):
        for headers in ({'X-Panel-Request': ''}, {'Sec-Fetch-Site': 'cross-site'}):
            code, _ = self.request('/api/refresh', {'fetch': True}, headers)
            self.assertEqual(code, 403)
        self.assertFalse(panel.worker.STATE.exists())

    def test_refresh_modes_and_throttle(self):
        code, _ = self.request('/api/refresh', {'fetch': 'false'})
        self.assertEqual(code, 400)
        code, _ = self.request('/api/refresh', {'fetch': False})
        self.assertEqual(code, 200)
        path = panel.worker.STATE / 'refresh.request'
        previous = path.read_bytes()
        self.assertFalse(json.loads(previous)['fetch'])
        code, _ = self.request('/api/refresh', {'fetch': True})
        self.assertEqual(code, 429)
        self.assertEqual(path.read_bytes(), previous)
        request = json.loads(previous)
        request['time'] -= 11
        panel.worker.atomic(panel.worker.STATE / 'running.json', json.dumps({'request_id': request['id'], 'busy': False}))
        path.write_text(json.dumps(request), encoding='utf-8')
        code, _ = self.request('/api/refresh', {'fetch': True})
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(path.read_bytes())['fetch'])

    def test_invalid_config_is_not_saved(self):
        _, current = self.request('/api/config')
        current['config']['sources'][0]['id'] = 'status'
        before = self.config.read_bytes()
        code, _ = self.request('/api/config', current)
        self.assertEqual(code, 400)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse(panel.worker.STATE.exists())

    def test_unauthenticated_write_is_rejected(self):
        handler = object.__new__(panel.Handler)
        handler.headers = {'X-Panel-Request': '1'}
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        with patch.object(panel, 'AUTH_DISABLED', False):
            handler.do_POST()
        handler.send_response.assert_called_once_with(401)
        self.assertFalse(panel.worker.STATE.exists())

    def test_oversized_write_is_rejected(self):
        code, _ = self.request('/api/refresh', {'fetch': True}, {'Content-Length': str(panel.worker.LIMIT + 1)})
        self.assertEqual(code, 400)
        self.assertFalse(panel.worker.STATE.exists())

    def test_single_airport_refresh_validation_and_busy_conflict(self):
        for sid in ('missing', 'airport_b', '../status', 123):
            code, _ = self.request('/api/refresh', {'fetch': True, 'source_id': sid})
            self.assertEqual(code, 400)
        code, _ = self.request('/api/refresh', {'fetch': False, 'source_id': 'airport_a'})
        self.assertEqual(code, 200)
        path = panel.worker.STATE / 'refresh.request'
        request = json.loads(path.read_bytes())
        self.assertEqual(request['source_id'], 'airport_a')
        self.assertFalse(request['fetch'])
        request['time'] -= 11
        panel.worker.atomic(path, json.dumps(request))
        code, _ = self.request('/api/refresh', {'fetch': True})
        self.assertEqual(code, 409)

    def test_node_details_do_not_expose_credentials(self):
        source = self.cfg['sources'][0]
        node = {'name':'airport_a::1::Japan', 'type':'ss', 'server':'example.com', 'port':443, 'password':'NODE_SECRET', 'private-key':'KEY_SECRET'}
        panel.worker.atomic(panel.worker.STATE / 'airport_a.json', json.dumps({'nodes':[node], 'health':{node['name']:True}, 'delays':{node['name']:87}, 'checked_at':100}))
        code, result = self.request('/api/nodes')
        self.assertEqual(code, 200)
        self.assertEqual(result['nodes'][0]['delay_ms'], 87)
        self.assertEqual(result['nodes'][0]['source_id'], source['id'])
        self.assertNotIn('SECRET', json.dumps(result))

    def test_bulk_exclusions_persist_with_publish_only_request(self):
        _, current = self.request('/api/config')
        current['config']['sources'][0]['excluded_nodes'] = ['a'*64, 'b'*64]
        code, _ = self.request('/api/config', current)
        self.assertEqual(code, 200)
        cfg = panel.worker.load_config()
        self.assertEqual(cfg['sources'][0]['excluded_nodes'], ['a'*64,'b'*64])
        request = panel.worker.read_json(panel.worker.STATE / 'refresh.request', {})
        self.assertTrue(request['publish_only'])
        self.assertFalse(request['fetch'])


if __name__ == '__main__':
    unittest.main()
