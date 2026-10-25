import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

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
        self.probe = patch.object(worker, 'probe', side_effect=lambda nodes, cfg, measurements=None: nodes).start()
        self.cfg = {'fetch_interval': 3600, 'retry_interval': 900, 'snapshot_max_age': 604800,
                    'probe_urls': ['https://example.com'],
                    'sources': [{'id': 'a', 'enabled': True}, {'id': 'b', 'enabled': True}]}
        self.nodes = worker.parse_nodes('proxies:\n- name: test\n  type: ss\n  server: example.com\n  port: 443\n  cipher: aes-128-gcm\n  password: secret\n', 'a')
        self.fetch.return_value = self.nodes

    def status(self):
        return json.loads((worker.STATE / 'status.json').read_text())

    def test_logs_are_bounded_rotated_and_exclude_raw_secrets(self):
        with patch('builtins.print'):
            worker.log_event('fetch_done', 'a', count=5, url='https://private/token', password='secret', content='private YAML')
        entry = worker.recent_logs()[0]
        self.assertEqual(entry['count'], 5)
        self.assertNotIn('private', json.dumps(entry))
        self.assertNotIn('secret', json.dumps(entry))
        path = worker.STATE/'worker.log'
        path.write_text('x'*1024*1024, encoding='utf-8')
        with patch('builtins.print'):
            worker.log_event('task_done', 'a')
        self.assertTrue((worker.STATE/'worker.log.1').exists())
        self.assertLess(path.stat().st_size, 1024)
        with path.open('a', encoding='utf-8') as stream:
            stream.write('broken partial line\n')
            for i in range(250):
                stream.write(json.dumps({'time':i, 'service':'worker','event':'probe_progress','done':i})+'\n')
        entries = worker.recent_logs()
        self.assertEqual(len(entries), 200)
        self.assertEqual(entries[-1]['event'], 'task_done')

    def test_new_request_cancels_old_cycle_before_writing_stale_nodes(self):
        worker.atomic(worker.STATE/'refresh.request', json.dumps({'id':'new'}))
        worker.cycle(dict(self.cfg, _request_id='old'))
        self.fetch.assert_not_called()
        self.assertFalse((worker.PUBLIC/'clash.yaml').exists())
        self.assertTrue(worker.request_superseded({'_request_id':'old'}))
        self.assertFalse(worker.request_superseded({'_request_id':'new'}))

    def test_file_nodes_visible_and_published_without_fetch_or_probe(self):
        content = 'proxies:\n- name: file node\n  type: ss\n  server: example.com\n  port: 443\n  cipher: aes-128-gcm\n  password: secret\n'
        source = dict(id='file', enabled=True, subscription_type='file', yaml_content=content)
        self.cfg['sources'].append(source)
        self.assertEqual(len(worker.node_details(self.cfg)), 1)
        worker.cycle(self.cfg, publish_only=True)
        self.fetch.assert_not_called()
        self.probe.assert_not_called()
        self.assertEqual(self.status()['sources']['file']['cached'], 1)
        self.assertEqual(self.status()['published'], 1)
        self.assertIn('file node', (worker.PUBLIC/'clash.yaml').read_text('utf-8'))
        cache = worker.source_cache(source)
        cache['health'] = {cache['nodes'][0]['name']: False}
        worker.atomic(worker.STATE/'file.json', json.dumps(cache))
        source['yaml_content'] = content.replace('example.com', 'replacement.com')
        self.assertIsNone(worker.node_details(self.cfg)[0]['healthy'])
        worker.cycle(self.cfg, publish_only=True)
        self.assertIn('replacement.com', (worker.PUBLIC/'clash.yaml').read_text('utf-8'))

    def test_source_counts_distinguish_total_published_and_healthy(self):
        worker.cycle(self.cfg)
        self.cfg['sources'][0]['excluded_nodes'] = [worker.node_id(self.nodes[0])]
        worker.cycle(self.cfg, publish_only=True)
        self.assertEqual(self.status()['sources']['a']['cached'], 1)
        self.assertEqual(self.status()['sources']['a']['healthy'], 1)
        self.assertEqual(self.status()['sources']['a']['published'], 0)
        self.assertEqual(self.status()['sources']['b']['published'], 1)
        worker.cycle(self.cfg, publish_only=True, rules_ready=False)
        self.assertTrue(all(s['published'] == 0 for s in self.status()['sources'].values()))

    def test_rule_switch_and_unhealthy_exclusion_follow_cached_health(self):
        worker.cycle(self.cfg)
        self.cfg['exclude_rules'] = [{'name_contains': 'test', 'enabled': False}]
        self.cfg['exclude_unhealthy'] = True
        cache = worker.read_json(worker.STATE / 'a.json', {})
        cache['health'][self.nodes[0]['name']] = False
        worker.atomic(worker.STATE / 'a.json', json.dumps(cache))
        worker.cycle(self.cfg, publish_only=True)
        self.assertEqual(self.status()['published'], 1)
        self.assertEqual(worker.node_details(self.cfg)[0]['excluded'], 'rule')
        cache['health'] = {}
        worker.atomic(worker.STATE / 'a.json', json.dumps(cache))
        worker.cycle(self.cfg, publish_only=True)
        self.assertEqual(self.status()['published'], 2, 'Unknown health must be retained')
        cache['health'][self.nodes[0]['name']] = True
        worker.atomic(worker.STATE / 'a.json', json.dumps(cache))
        worker.cycle(self.cfg, publish_only=True)
        self.assertEqual(self.status()['published'], 2, 'Recovered nodes must be restored')
        self.cfg['exclude_rules'][0]['enabled'] = True
        worker.cycle(self.cfg, publish_only=True)
        self.assertEqual(self.status()['published'], 0)
        self.cfg['exclude_rules'][0]['enabled'] = False
        worker.cycle(self.cfg, publish_only=True)
        self.assertEqual(self.status()['published'], 2)

    def test_exclusion_switches_require_booleans(self):
        import yaml
        cfg = yaml.safe_load(Path('config/sources.example.yaml').read_text('utf-8'))
        for value in (None, 1, 'false', []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                worker.validate_config(dict(cfg, exclude_unhealthy=value))
            with self.subTest(value=value), self.assertRaises(ValueError):
                worker.validate_config(dict(cfg, exclude_rules=[{'name_contains': 'test', 'enabled': value}]))

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
        self.probe.side_effect = lambda nodes, cfg, measurements=None: []
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
        self.probe.side_effect = lambda nodes, cfg, measurements=None: []
        worker.cycle(self.cfg)
        self.assertEqual(self.status()['published'], 1)
        self.assertNotIn('b', self.status()['sources'])

    def test_valid_new_subscription_replaces_offline_old_nodes(self):
        worker.cycle(self.cfg)
        new = copy.deepcopy(self.nodes)
        new[0]['name'] = 'new-node'
        self.fetch.return_value = new
        self.probe.side_effect = lambda nodes, cfg, measurements=None: []
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

    def test_country_group_toggle(self):
        nodes = [dict(self.nodes[0], name='a::1::Japan')]
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                output = worker.client_config(nodes, dict(self.cfg, group_by_country=enabled))
                groups = {g['name']: g for g in output['proxy-groups']}
                self.assertEqual('🇯🇵 日本' in groups, enabled)
                self.assertEqual(groups['AUTO']['proxies'], [nodes[0]['name']])
                self.assertEqual(groups['PROXY']['proxies'],
                                 ['AUTO'] + (['🇯🇵 日本'] if enabled else []) + [nodes[0]['name']])
                self.assertEqual(output['proxies'], nodes)

    def test_selected_country_groups(self):
        nodes = [dict(self.nodes[0], name=n) for n in ['a::1::香港', 'a::2::Japan', 'a::3::USA', 'a::4::unknown']]
        for selection in (None, ['🇭🇰 香港', '🇯🇵 日本'], [], ['🇩🇪 德国']):
            with self.subTest(selection=selection):
                groups = {g['name']: g for g in worker.client_config(nodes, dict(self.cfg, country_groups=selection))['proxy-groups']}
                if selection is None:
                    self.assertIn('🇺🇸 美国', groups)
                    self.assertNotIn('🌐 其他国家', groups)
                else:
                    separate = [n['name'] for n in nodes if worker.country(n['name']) in selection]
                    self.assertEqual(groups['🌐 其他国家']['proxies'], [n['name'] for n in nodes if n['name'] not in separate])
                    self.assertNotIn('🇩🇪 德国', groups)
                    self.assertNotIn('🇺🇸 美国', groups)
                self.assertEqual(groups['AUTO']['proxies'], [n['name'] for n in nodes])
                for label in groups:
                    if label not in ('AUTO', 'PROXY'):
                        self.assertIn(label, groups['PROXY']['proxies'])
        groups = worker.client_config(nodes, dict(self.cfg, group_by_country=False, country_groups=[]))['proxy-groups']
        self.assertEqual([g['name'] for g in groups], ['PROXY', 'AUTO'])

    def test_country_selection_validation(self):
        import yaml
        cfg = yaml.safe_load(Path('config/sources.example.yaml').read_text('utf-8'))
        for value in (None, [], ['🇭🇰 香港', '🇯🇵 日本'], ['🇵🇱 PL']):
            worker.validate_config(dict(cfg, country_groups=value))
        for value in (True, '🇭🇰 香港', [None], ['AUTO'], ['🌐 其他地区'], ['🇯🇵 日本'] * 2):
            with self.subTest(value=value), self.assertRaises(ValueError):
                worker.validate_config(dict(cfg, country_groups=value))

    def test_chatgpt_group_toggle(self):
        for countries in (True, False):
            for enabled in (True, False):
                cfg = dict(self.cfg, group_by_country=countries, chatgpt_group=enabled)
                output = worker.client_config(self.nodes, cfg)
                groups = {g['name']: g for g in output['proxy-groups']}
                self.assertEqual('ChatGPT' in groups, enabled)
                self.assertEqual('ChatGPT' in groups['PROXY']['proxies'], enabled)
                if enabled:
                    self.assertEqual(groups['ChatGPT']['type'], 'url-test')
                    self.assertEqual(groups['ChatGPT']['url'], 'https://chatgpt.com/')
                    self.assertEqual(groups['ChatGPT']['proxies'], groups['AUTO']['proxies'])
        self.assertNotIn('ChatGPT', [g['name'] for g in worker.client_config(self.nodes, self.cfg)['proxy-groups']])

    def test_check_only_does_not_fetch_due_sources(self):
        worker.cycle(self.cfg)
        self.clock.return_value += 4000
        self.fetch.reset_mock()
        worker.cycle(self.cfg, check_only=True)
        self.fetch.assert_not_called()
        self.assertEqual(self.status()['published'], 2)

    def test_targeted_refresh_keeps_other_airports_untouched(self):
        self.fetch.side_effect = lambda source, metadata: [dict(self.nodes[0], name=source['id']+'::1::Japan')]
        worker.cycle(self.cfg)
        before = (worker.STATE / 'b.json').read_bytes()
        self.clock.return_value += 4000
        self.fetch.reset_mock()
        self.probe.reset_mock()
        worker.cycle(self.cfg, force_fetch=True, source_id='a')
        self.assertEqual(self.fetch.call_count, 1)
        self.assertEqual(self.fetch.call_args.args[0]['id'], 'a')
        self.assertEqual(self.probe.call_count, 1)
        self.assertEqual((worker.STATE / 'b.json').read_bytes(), before)
        self.assertEqual(self.status()['published'], 2)
        self.fetch.reset_mock()
        worker.cycle(self.cfg, check_only=True, source_id='a')
        self.fetch.assert_not_called()

    def test_exclusions_keep_cache_and_never_restore_excluded_snapshot(self):
        worker.cycle(self.cfg)
        before = (worker.STATE / 'a.json').read_bytes()
        for source in self.cfg['sources']:
            source['excluded_nodes'] = [worker.node_id(self.nodes[0])]
        self.fetch.reset_mock()
        self.probe.reset_mock()
        worker.cycle(self.cfg, publish_only=True)
        self.fetch.assert_not_called()
        self.probe.assert_not_called()
        self.assertEqual((worker.STATE / 'a.json').read_bytes(), before)
        self.assertEqual(self.status()['published'], 0)
        self.assertFalse((worker.PUBLIC / 'clash.yaml').exists())
        self.cfg['sources'][0]['excluded_nodes'] = []
        worker.cycle(self.cfg, publish_only=True)
        self.assertEqual(self.status()['published'], 1)
        self.assertTrue((worker.PUBLIC / 'clash.yaml').exists())

    def test_rule_exclusion_applies_to_new_nodes_and_identity_survives_reorder(self):
        node = self.nodes[0]
        self.assertEqual(worker.node_id(node), worker.node_id(dict(node, name='a::20::renamed')))
        self.assertNotEqual(worker.node_id(node), worker.node_id(dict(node, password='other')))
        self.cfg['exclude_rules'] = [{'source_id': 'a', 'name_contains': 'TEST'}]
        worker.cycle(self.cfg)
        self.assertEqual(self.status()['published'], 1)
        self.assertEqual(worker.node_details(self.cfg)[0]['excluded'], 'rule')

    def test_combined_rules_scope_and_future_nodes(self):
        self.cfg['exclude_rules'] = [{'source_id':'a','country':'🇯🇵 日本'},
                                    {'country':'🇬🇧 英国','protocol':'vless'}]
        def fetched(source, metadata):
            return [dict(self.nodes[0], name=source['id']+'::'+str(i)+'::'+name, type=protocol)
                    for i,(name,protocol) in enumerate([('Japan','ss'),('UK','vless'),('UK','ss'),('USA','vless')])]
        self.fetch.side_effect = fetched
        worker.cycle(self.cfg)
        self.assertEqual(self.status()['published'],5)
        self.assertEqual(sum(n['excluded']=='rule' for n in worker.node_details(self.cfg)),3)
        self.clock.return_value+=4000
        def later(source, metadata):
            return fetched(source, metadata)+[dict(self.nodes[0],name=source['id']+'::9::UK new',type='vless')]
        self.fetch.side_effect=later
        worker.cycle(self.cfg,force_fetch=True)
        self.assertEqual(self.status()['published'],5)
        self.assertEqual(sum(n['excluded']=='rule' for n in worker.node_details(self.cfg)),5)
        rule={'source_id':'a','country':'🇬🇧 英国','protocol':'vless','name_contains':'PREMIUM'}
        node=dict(self.nodes[0],name='a::1::UK Premium',type='vless')
        self.assertTrue(worker.rule_matches(node,'a',rule))
        self.assertFalse(worker.rule_matches(node,'b',rule))
        self.assertFalse(worker.rule_matches(dict(node,type='ss'),'a',rule))
        self.assertFalse(worker.rule_matches(dict(node,name='a::1::UK basic'),'a',rule))

    def test_combined_rule_validation(self):
        import yaml
        cfg=yaml.safe_load(Path('config/sources.example.yaml').read_text('utf-8'))
        for rule in ({'source_id':'airport_a','country':'🇯🇵 日本'}, {'country':'🇬🇧 英国','protocol':'vless'},
                     {'name_contains':'高倍率'}, {'protocol':'vless'}):
            worker.validate_config(dict(cfg,exclude_rules=[rule]))
        for rule in ({}, {'source_id':'airport_a'}, {'country':123}, {'protocol':'VLESS'},
                     {'country':'日本'}, {'name_contains':' '}, {'protocol':True}):
            with self.subTest(rule=rule),self.assertRaises(ValueError):
                worker.validate_config(dict(cfg,exclude_rules=[rule]))

    def test_delay_and_check_time_cached_without_changing_nodes(self):
        def measured(nodes, cfg, measurements):
            measurements[nodes[0]['name']] = 42
            return nodes
        self.probe.side_effect = measured
        worker.cycle(self.cfg)
        detail = worker.node_details(self.cfg)[0]
        self.assertEqual(detail['delay_ms'], 42)
        self.assertEqual(detail['checked_at'], 1000000)
        self.probe.side_effect = lambda nodes, cfg, measurements: []
        self.clock.return_value += 60
        worker.cycle(self.cfg, check_only=True)
        detail = worker.node_details(self.cfg)[0]
        self.assertIsNone(detail['delay_ms'])
        self.assertFalse(detail['healthy'])
        self.assertEqual(detail['checked_at'], 1000060)
        self.assertNotIn('password', json.dumps(detail))

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

    def test_missing_rules_still_fetches_and_probes_without_publishing(self):
        cfg = dict(self.cfg, public_base_url='https://example.com/token', health_interval=60)
        with patch.object(worker, 'load_config', return_value=cfg), patch.object(worker.requests, 'Session') as session:
            session.return_value.__enter__.return_value.get.side_effect = worker.requests.ConnectionError('secret URL')
            worker.run_once(None)
            self.assertEqual(self.fetch.call_count, 2)
            self.assertEqual(self.probe.call_count, 2)
            self.assertFalse((worker.PUBLIC / 'clash.yaml').exists())
            self.assertEqual(self.status()['state'], 'rules_pending')
            self.assertEqual(self.status()['published'], 0)
            running = worker.read_json(worker.STATE / 'running.json', {})
            self.assertFalse(running['busy'])
            self.assertEqual(running['error'], 'ValueError')
            self.assertNotIn('secret', json.dumps(running))
        with patch.object(worker, 'load_config', return_value=cfg), patch.object(worker, 'update_rules', return_value=True):
            worker.run_once(None)
        self.assertTrue((worker.PUBLIC / 'clash.yaml').exists())
        running = worker.read_json(worker.STATE / 'running.json', {})
        self.assertIsNone(running['error'])
        self.assertIn('last_success_at', running)
        self.assertIn('last_failure_at', running)

    def test_failure_keeps_success_time_and_published_file(self):
        cfg = dict(self.cfg, health_interval=60)
        with patch.object(worker, 'load_config', return_value=cfg):
            worker.run_once(None)
        original = (worker.PUBLIC / 'clash.yaml').read_bytes()
        self.clock.return_value += 60
        with patch.object(worker, 'load_config', side_effect=ValueError('private config')):
            worker.run_once(None)
        running = worker.read_json(worker.STATE / 'running.json', {})
        self.assertEqual(running['last_success_at'], 1000000)
        self.assertEqual(running['last_failure_at'], 1000060)
        self.assertEqual((worker.PUBLIC / 'clash.yaml').read_bytes(), original)

    def test_run_once_consumes_check_only_request_once(self):
        cfg = dict(self.cfg, health_interval=60)
        worker.cycle(cfg)
        self.clock.return_value += 4000
        self.fetch.reset_mock()
        worker.atomic(worker.STATE / 'refresh.request', json.dumps({'id': 'check', 'fetch': False}))
        with patch.object(worker, 'load_config', return_value=cfg):
            interval, consumed = worker.run_once(None)
            self.assertEqual((interval, consumed), (60, 'check'))
            self.fetch.assert_not_called()
            worker.run_once(consumed)
            self.assertEqual(self.fetch.call_count, 2)

    def test_missing_rules_revokes_old_file_and_removed_source(self):
        worker.cycle(self.cfg)
        self.cfg['sources'][1]['enabled'] = False
        worker.cycle(self.cfg, rules_ready=False)
        self.assertFalse((worker.PUBLIC / 'clash.yaml').exists())
        self.assertNotIn('b', self.status()['sources'])


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


class ProbeTests(unittest.TestCase):
    def test_probe_records_delay_and_cleans_up_core(self):
        main, request = Mock(), Mock()
        main.headers = {}
        request.__enter__ = Mock(return_value=request)
        request.__exit__ = Mock(return_value=False)
        request.get.return_value.json.return_value = {'delay': 53}
        process = Mock()
        process.poll.return_value = None
        node = {'name':'a::1::Japan','type':'ss','server':'example.com','port':443}
        cfg = {'probe_urls':['https://example.com'],'probe_timeout_ms':5000,'probe_workers':1}
        with tempfile.TemporaryDirectory(dir=os.environ.get('TEST_TMP')) as tmp:
            with patch.object(worker.tempfile, 'TemporaryDirectory') as directory, patch.object(worker.requests, 'Session', side_effect=[main,request]), patch.object(worker.subprocess, 'run', return_value=Mock(returncode=0)), patch.object(worker.subprocess, 'Popen', return_value=process), patch.object(worker, 'log_event') as progress:
                directory.return_value.__enter__.return_value = tmp
                measured = {}
                self.assertEqual(worker.probe([node], cfg, measured), [node])
                self.assertEqual(measured, {node['name']:53})
                progress.assert_called_once_with('probe_progress', node['name'].split('::',1)[0], done=1, total=1, healthy=1)
                process.terminate.assert_called_once()
                main.close.assert_called_once()


class DisplayFieldsTests(unittest.TestCase):
    def test_file_subscription_validation_and_fetch(self):
        import yaml
        cfg = yaml.safe_load(Path('config/sources.example.yaml').read_text('utf-8'))
        source = cfg['sources'][0]
        source.update(subscription_type='file', url='', yaml_content='proxies:\n- name: test\n  type: ss\n  server: example.com\n  port: 443\n  cipher: aes-128-gcm\n  password: secret\n')
        worker.validate_config(cfg)
        with patch.object(worker.requests, 'Session', side_effect=AssertionError('network used')):
            metadata = {}
            self.assertEqual(len(worker.fetch(source, metadata)), 1)
            self.assertIsNone(metadata['subscription_info'])
        for content in ('', 'proxies: []', 'proxies: [', 'proxies: [{name: bad, type: direct}]', 'x'*(worker.LIMIT+1)):
            with self.subTest(content=content[:30]), self.assertRaises(ValueError):
                worker.validate_config(dict(cfg, sources=[dict(source, yaml_content=content)]))
        with self.assertRaises(ValueError):
            worker.validate_config(dict(cfg, sources=[dict(source, subscription_type='other')]))

    def test_exclusion_validation(self):
        import yaml
        cfg = yaml.safe_load(Path('config/sources.example.yaml').read_text('utf-8'))
        for value in ('bad', [123], ['../status'], ['a'*64]*1001):
            bad = copy.deepcopy(cfg)
            bad['sources'][0]['excluded_nodes'] = value
            with self.subTest(value=str(value)[:30]), self.assertRaises(ValueError):
                worker.validate_config(bad)
        for rules in ({}, [{}], [{'source_id':'missing','name_contains':'test'}], [{'name_contains':''}], [{'name_contains':123}]):
            bad = copy.deepcopy(cfg)
            bad['exclude_rules'] = rules
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                worker.validate_config(bad)
        cfg['sources'][0]['excluded_nodes'] = ['a'*64]
        cfg['exclude_rules'] = [{'source_id':'airport_a','name_contains':'高倍率'}]
        worker.validate_config(cfg)

    def test_reserved_ids_and_invalid_urls(self):
        import yaml
        cfg = yaml.safe_load(Path('config/sources.example.yaml').read_text('utf-8'))
        for sid in ('status', 'running', 'published', 'rules-status', 'STATUS'):
            bad = copy.deepcopy(cfg)
            bad['sources'][0]['id'] = sid
            with self.subTest(id=sid), self.assertRaises(ValueError):
                worker.validate_config(bad)
        for key, values in [('public_base_url', ['http://example.com', 'https://', 'https://user:pass@example.com', 'https://example.com?token=x', 123]),
                            ('rules_fetch_proxy', ['ftp://example.com', 'socks5h://', 'http://example.com:bad', 123])]:
            for value in values:
                bad = copy.deepcopy(cfg)
                bad[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    worker.validate_config(bad)
        for key, values in [('url', ['', 'https://', 'https://example.com:bad', 123]),
                            ('fetch_proxy', ['http://', 'ftp://example.com', 123])]:
            for value in values:
                bad = copy.deepcopy(cfg)
                bad['sources'][0][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    worker.validate_config(bad)
        cfg['sources'][1]['url'] = ''
        cfg['rules_fetch_proxy'] = 'socks5h://user:pass@proxy.example.com:1080'
        worker.validate_config(cfg)

    def test_chatgpt_group_validation(self):
        import yaml
        cfg = yaml.safe_load(Path('config/sources.example.yaml').read_text('utf-8'))
        cfg.pop('chatgpt_group')
        worker.validate_config(cfg)
        for value in (True, False):
            cfg['chatgpt_group'] = value
            worker.validate_config(cfg)
        for value in ('false', 0, 1, None, []):
            cfg['chatgpt_group'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                worker.validate_config(cfg)

    def test_group_by_country_validation(self):
        import yaml
        cfg = yaml.safe_load(Path('config/sources.example.yaml').read_text('utf-8'))
        cfg.pop('group_by_country')
        worker.validate_config(cfg)
        for value in (True, False):
            cfg['group_by_country'] = value
            self.assertEqual(worker.validate_config(cfg)['group_by_country'], value)
        for value in ('false', 0, 1, None, []):
            cfg['group_by_country'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                worker.validate_config(cfg)

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
