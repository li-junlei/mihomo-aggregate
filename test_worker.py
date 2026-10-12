import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import worker


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get('TEST_TMP'))
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.addCleanup(patch.stopall)
        patch.object(worker, 'STATE', root / 'state').start()
        patch.object(worker, 'PUBLIC', root / 'public').start()
        self.clock = patch.object(worker.time, 'time', return_value=1000000).start()
        self.fetch = patch.object(worker, 'fetch').start()
        self.probe = patch.object(worker, 'probe', side_effect=lambda nodes, cfg: nodes).start()
        self.cfg = {'fetch_interval': 3600, 'retry_interval': 900, 'snapshot_max_age': 604800,
                    'probe_urls': ['https://example.com'],
                    'sources': [{'id': 'a', 'enabled': True}, {'id': 'b', 'enabled': True}]}
        self.nodes = worker.parse_nodes('proxies:\n- name: test\n  type: ss\n  server: example.com\n  port: 443\n  cipher: aes-128-gcm\n  password: secret\n', 'a')
        self.fetch.return_value = self.nodes

    def status(self):
        return json.loads((worker.STATE / 'status.json').read_text())

    def test_failure_keeps_each_airport_and_no_request_from_publish(self):
        worker.cycle(self.cfg)
        self.clock.return_value += 4000
        self.fetch.side_effect = ValueError('expired URL')
        worker.cycle(self.cfg)
        self.assertEqual(self.status()['healthy'], 2)
        self.assertEqual(self.status()['state'], 'fresh')
        text = (worker.PUBLIC / 'clash.yaml').read_text('utf-8')
        self.assertNotIn('proxy-providers', text)
        self.assertNotIn('expired', text)

    def test_bad_candidate_does_not_destroy_good_cache(self):
        worker.cycle(self.cfg)
        self.clock.return_value += 4000
        self.probe.side_effect = [ValueError('invalid'), self.nodes, [], self.nodes]
        worker.cycle(self.cfg)
        self.assertEqual(self.status()['healthy'], 1)
        self.assertEqual(self.status()['published'], 2)

    def test_temporarily_dead_nodes_retained_indefinitely(self):
        worker.cycle(self.cfg)
        self.probe.side_effect = lambda nodes, cfg: []
        self.clock.return_value += 4000
        worker.cycle(self.cfg)
        self.assertEqual(self.status()['state'], 'retained')
        self.clock.return_value += 604801
        worker.cycle(self.cfg)
        self.assertEqual(self.status()['state'], 'retained')
        self.assertEqual(self.status()['published'], 2)

    def test_disabled_airport_never_retained_in_stale_snapshot(self):
        worker.cycle(self.cfg)
        self.cfg['sources'][1]['enabled'] = False
        self.probe.side_effect = lambda nodes, cfg: []
        worker.cycle(self.cfg)
        self.assertEqual(self.status()['published'], 1)
        self.assertNotIn('b', self.status()['sources'])

    def test_valid_new_subscription_replaces_offline_old_nodes(self):
        worker.cycle(self.cfg)
        new = copy.deepcopy(self.nodes)
        new[0]['name'] = 'new-node'
        self.fetch.return_value = new
        self.probe.side_effect = lambda nodes, cfg: []
        self.clock.return_value += 4000
        worker.cycle(self.cfg)
        self.assertIn('new-node', (worker.PUBLIC / 'clash.yaml').read_text('utf-8'))
        self.assertEqual(self.status()['published'], 2)

    def test_country_groups_and_domestic_rules(self):
        nodes = [dict(self.nodes[0], name=n) for n in ['a::1::香港 HK', 'a::2::Japan',
                                                      'a::3::🇯🇵 日本', 'a::4::印度尼西亚']]
        cfg = dict(self.cfg, public_base_url='https://example.com/secret')
        output = worker.client_config(nodes, cfg)
        groups = {g['name']: g for g in output['proxy-groups']}
        self.assertEqual(len(groups['🇯🇵 日本']['proxies']), 2)
        self.assertIn('🇮🇩 印尼', groups)
        self.assertIn('RULE-SET,cn_domain,DIRECT', output['rules'])
        self.assertEqual(output['rules'][-1], 'MATCH,PROXY')
        self.assertTrue(output['rule-providers']['cn_ip']['url'].startswith('https://example.com/secret/'))

    def test_invalid_inputs(self):
        for body in ('<html>login</html>', 'proxies: []',
                     'proxies: [{name: bad, type: direct}]',
                     'proxies: [{name: bad, type: ss, server: host, dialer-proxy: other}]'):
            with self.assertRaises(ValueError):
                worker.parse_nodes(body, 'a')

    def test_check_only_does_not_fetch_due_sources(self):
        worker.cycle(self.cfg)
        self.clock.return_value += 4000
        self.fetch.reset_mock()
        worker.cycle(self.cfg, check_only=True)
        self.fetch.assert_not_called()
        self.assertEqual(self.status()['published'], 2)

    def test_rule_download_and_failed_refresh_keeps_files(self):
        cfg = dict(self.cfg, public_base_url='https://example.com/secret')
        with patch.object(worker.requests, 'Session') as session:
            response = session.return_value.__enter__.return_value.get.return_value.__enter__.return_value
            response.iter_content.side_effect = [[b'payload:\n - +.cn\n'], [b'payload:\n - 1.0.1.0/24\n']]
            worker.update_rules(cfg)
            target = worker.PUBLIC / 'rules/cn-domain.yaml'
            original = target.read_bytes()
            self.clock.return_value += 86401
            session.return_value.__enter__.return_value.get.side_effect = worker.requests.ConnectionError()
            worker.update_rules(cfg)
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(worker.read_json(worker.STATE / 'rules-status.json', {})['error'], 'ConnectionError')


class SubscriptionInfoTests(unittest.TestCase):
    def test_header_and_missing_fields(self):
        info = worker.subscription_info('upload=100; download=200; total=1000; expire=1800000000')
        self.assertEqual(info['remaining_bytes'], 700)
        self.assertEqual(info['expires_at'], 1800000000)
        self.assertEqual(worker.subscription_info('upload=0;download=2000;total=1000')['remaining_bytes'], 0)
        self.assertIsNone(worker.subscription_info('upload=-1;total=oops;expire=0'))
        self.assertIsNone(worker.subscription_info(None))
        self.assertNotIn('remaining_bytes', worker.subscription_info('expire=1800000000'))

    def test_fetch_failure_retains_metadata(self):
        case = CacheTests()
        case.setUp()
        try:
            def fetched(source, metadata):
                metadata['subscription_info'] = worker.subscription_info('upload=0;download=10;total=100')
                return case.nodes
            case.fetch.side_effect = fetched
            worker.cycle(case.cfg)
            case.fetch.side_effect = ValueError('expired')
            case.clock.return_value += 4000
            worker.cycle(case.cfg)
            self.assertEqual(case.status()['sources']['a']['subscription_info']['remaining_bytes'], 90)
        finally:
            case.doCleanups()


class DisplayFieldsTests(unittest.TestCase):
    def test_name_and_website_validation(self):
        import yaml
        cfg = yaml.safe_load(Path('config/sources.example.yaml').read_text('utf-8'))
        source = cfg['sources'][0]
        source.update(name='测试机场', website='https://example.com/account')
        self.assertEqual(worker.validate_config(cfg)['sources'][0]['name'], '测试机场')
        for website in ('javascript:alert(1)', 'https://user:pass@example.com', 'https://', 123):
            source['website'] = website
            with self.assertRaises(ValueError):
                worker.validate_config(cfg)
        source['website'] = ''
        source['name'] = 'x' * 81
        with self.assertRaises(ValueError):
            worker.validate_config(cfg)


if __name__ == '__main__':
    unittest.main()
