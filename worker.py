"""Scheduled native Clash YAML fetch, per-source cache, real Mihomo probes, static publish."""
import concurrent.futures
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import time
import threading
from urllib.parse import quote, urlparse

import requests
import yaml

STATE = Path('/state')
PUBLIC = Path('/public')
CONFIG = Path('/config/sources.yaml')
LIMIT = 4 * 1024 * 1024


_LOG_LOCK = threading.Lock()


def log_event(event, source_id=None, service='worker', **fields):
    entry = {'time': time.time(), 'service': service, 'event': event}
    if source_id:
        entry['source_id'] = source_id
    # Only counts and exception class names may enter logs; never include raw upstream data.
    entry.update({k: v for k, v in fields.items() if k in ('total', 'count', 'done', 'healthy', 'published', 'cached') and isinstance(v, int)})
    if fields.get('error'):
        entry['error'] = fields['error']
    line = json.dumps(entry, ensure_ascii=False)
    print(line, flush=True)
    try:
        with _LOG_LOCK:
            STATE.mkdir(parents=True, exist_ok=True)
            path = STATE / (service + '.log')
            if path.exists() and path.stat().st_size >= 1024 * 1024:
                os.replace(path, STATE / (service + '.log.1'))
            with path.open('a', encoding='utf-8') as stream:
                stream.write(line + '\n')
            os.chmod(path, 0o600)
    except OSError:
        pass  # Container stdout remains available if the log mirror cannot be written.


def recent_logs():
    entries = []
    for service in ('worker', 'panel'):
        for suffix in ('.log.1', '.log'):
            try:
                with (STATE / (service + suffix)).open('rb') as stream:
                    stream.seek(0, 2)
                    stream.seek(max(0, stream.tell() - 128 * 1024))
                    lines = stream.read().decode('utf-8', 'replace').splitlines()
            except FileNotFoundError:
                continue
            for line in lines:
                try:
                    entry = json.loads(line)
                    if isinstance(entry, dict) and isinstance(entry.get('time'), (int, float)):
                        entries.append(entry)
                except (ValueError, TypeError):
                    continue
    return sorted(entries, key=lambda e: e['time'])[-200:]


def atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_json(path, default):
    return json.loads(path.read_text('utf-8')) if path.exists() else default


def parse_nodes(text, source_id):
    data = yaml.safe_load(text)
    nodes = data.get('proxies') if isinstance(data, dict) else None
    if not isinstance(nodes, list) or not 0 < len(nodes) <= 1000:
        raise ValueError('expected nonempty native Clash proxies list (max 1000)')
    result = []
    for i, node in enumerate(nodes):
        if not isinstance(node, dict) or not isinstance(node.get('name'), str):
            raise ValueError('invalid node')
        if node.get('type') in ('direct', 'reject') or not node.get('server'):
            raise ValueError('only remote standalone nodes accepted')
        # Chains/local files are deliberately unsupported: isolated nodes only.
        if any(k in node for k in ('dialer-proxy', 'proxy', 'interface-name', 'routing-mark',
                                  'private-key-path', 'certificate', 'certificate-path')):
            raise ValueError('node depends on chains, local interfaces or files')
        n = copy.deepcopy(node)
        n['name'] = f'{source_id}::{i + 1}::{node["name"]}'
        result.append(n)
    return result


def subscription_info(header):
    fields = {}
    for part in (header or '').split(';'):
        key, sep, value = part.strip().partition('=')
        if sep and key in ('upload', 'download', 'total', 'expire') and re.fullmatch(r'[0-9]{1,16}', value.strip()):
            fields[key] = int(value)
    if not fields:
        return None
    result = {'updated_at': int(time.time())}
    if all(k in fields for k in ('upload', 'download', 'total')):
        result.update(total_bytes=fields['total'], used_bytes=fields['upload'] + fields['download'],
                      remaining_bytes=max(0, fields['total'] - fields['upload'] - fields['download']))
    if 0 < fields.get('expire', 0) <= 253402300799:
        result['expires_at'] = fields['expire']
    return result if len(result) > 1 else None


def fetch(source, metadata=None):
    if source.get('subscription_type', 'url') == 'file':
        if metadata is not None:
            metadata['subscription_info'] = None
        return parse_nodes(source['yaml_content'], source['id'])
    url = source['url']
    if urlparse(url).scheme != 'https':
        raise ValueError('upstream must use HTTPS')
    proxy = source.get('fetch_proxy')
    if proxy and urlparse(proxy).scheme not in ('http', 'https', 'socks5', 'socks5h'):
        raise ValueError('unsupported fetch proxy')
    with requests.Session() as session:
        session.trust_env = False
        if proxy:
            session.proxies = {'http': proxy, 'https': proxy}
        # No automatic redirects: prevents a signed URL silently moving to HTTP/local services.
        with session.get(url, headers=source.get('headers', {}), timeout=(10, 30),
                         stream=True, allow_redirects=False) as r:
            if r.status_code != 200:
                raise ValueError(f'upstream HTTP {r.status_code}')
            body = bytearray()
            deadline = time.monotonic() + 60
            for part in r.iter_content(65536):
                body.extend(part)
                if len(body) > LIMIT or time.monotonic() > deadline:
                    raise ValueError('upstream size/time limit')
            nodes = parse_nodes(body.decode('utf-8-sig'), source['id'])
            if metadata is not None:
                metadata['subscription_info'] = subscription_info(r.headers.get('subscription-userinfo'))
            return nodes


def client_config(nodes, cfg):
    names = [n['name'] for n in nodes]
    countries = {}
    if cfg.get('group_by_country', True):
        for n in nodes:
            label = country(n['name'])
            selected = cfg.get('country_groups')
            if selected is not None and label not in selected:
                label = '🌐 其他国家'
            countries.setdefault(label, []).append(n['name'])
    groups = [{'name': label, 'type': 'url-test', 'proxies': members,
               'url': cfg['probe_urls'][0], 'interval': 300, 'tolerance': 100, 'lazy': False}
              for label, members in sorted(countries.items())]
    if cfg.get('chatgpt_group', False):
        groups.append({'name': 'ChatGPT', 'type': 'url-test', 'proxies': names,
                       'url': 'https://chatgpt.com/', 'interval': 300,
                       'tolerance': 100, 'lazy': False})
    base = cfg.get('public_base_url', '')
    rule_providers = {key: {'type': 'http', 'behavior': behavior, 'format': 'yaml',
                           'url': base + '/rules/' + filename, 'path': './rules/' + filename,
                           'interval': 86400, 'proxy': 'DIRECT'}
                      for key, behavior, filename in [('cn_domain', 'domain', 'cn-domain.yaml'),
                                                       ('cn_ip', 'ipcidr', 'cn-ip.yaml')]} if base else {}
    return {'mixed-port': 7890, 'allow-lan': False, 'mode': 'rule', 'log-level': 'warning',
            'ipv6': False, 'proxies': nodes,
            'dns': {'enable': True, 'ipv6': False, 'enhanced-mode': 'fake-ip',
                    'fake-ip-range': '198.18.0.1/16',
                    'fake-ip-filter': ['*.lan', '*.local', 'localhost', '+.msftconnecttest.com', '+.msftncsi.com'],
                    'default-nameserver': ['223.5.5.5', '119.29.29.29'],
                    'proxy-server-nameserver': ['https://dns.alidns.com/dns-query'],
                    'direct-nameserver': ['https://dns.alidns.com/dns-query', 'https://doh.pub/dns-query'],
                    'nameserver': ['https://1.1.1.1/dns-query#PROXY', 'https://8.8.8.8/dns-query#PROXY'],
                    'nameserver-policy': {'rule-set:cn_domain': ['https://dns.alidns.com/dns-query',
                                                               'https://doh.pub/dns-query']} if base else {}},
            'rule-providers': rule_providers,
            'proxy-groups': [
                {'name': 'PROXY', 'type': 'select', 'proxies': ['AUTO'] + [g['name'] for g in groups] + names},
                {'name': 'AUTO', 'type': 'url-test', 'proxies': names,
                 'url': cfg['probe_urls'][0], 'interval': 300, 'tolerance': 100, 'lazy': False}] + groups,
            'rules': ['DOMAIN-SUFFIX,lan,DIRECT', 'DOMAIN-SUFFIX,local,DIRECT',
                      'DOMAIN,localhost,DIRECT', 'DOMAIN-SUFFIX,cn,DIRECT',
                      'IP-CIDR,127.0.0.0/8,DIRECT,no-resolve',
                      'IP-CIDR,10.0.0.0/8,DIRECT,no-resolve',
                      'IP-CIDR,172.16.0.0/12,DIRECT,no-resolve',
                      'IP-CIDR,192.168.0.0/16,DIRECT,no-resolve',
                      'IP-CIDR,169.254.0.0/16,DIRECT,no-resolve'] +
                     (['RULE-SET,cn_domain,DIRECT', 'RULE-SET,cn_ip,DIRECT'] if base else []) + ['MATCH,PROXY']}


def update_rules(cfg):
    if not cfg.get('public_base_url'):
        return True
    meta = read_json(STATE / 'rules-status.json', {})
    now = time.time()
    if now - meta.get('attempted', 0) < (3600 if meta.get('error') else 86400):
        return all((PUBLIC / 'rules' / f).exists() for f in ('cn-domain.yaml', 'cn-ip.yaml'))
    try:
        with requests.Session() as s:
            s.trust_env = False
            if cfg.get('rules_fetch_proxy'):
                s.proxies = {'https': cfg['rules_fetch_proxy']}
            for filename, remote in [('cn-domain.yaml', 'geosite'), ('cn-ip.yaml', 'geoip')]:
                url = f'https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/meta/geo/{remote}/cn.yaml'
                with s.get(url, timeout=(10, 30), stream=True) as r:
                    r.raise_for_status()
                    body = bytearray()
                    for chunk in r.iter_content(65536):
                        body.extend(chunk)
                        if len(body) > 16 * 1024 * 1024:
                            raise ValueError('rule file too large')
                data = yaml.safe_load(bytes(body))
                if not isinstance(data, dict) or not isinstance(data.get('payload'), list) or not data['payload']:
                    raise ValueError('invalid rules')
                atomic(PUBLIC / 'rules' / filename, body.decode('utf-8'))
        meta.update(updated_at=now, error=None)
    except Exception as e:
        meta['error'] = type(e).__name__
    meta['attempted'] = now
    atomic(STATE / 'rules-status.json', json.dumps(meta))
    return all((PUBLIC / 'rules' / f).exists() for f in ('cn-domain.yaml', 'cn-ip.yaml'))


COUNTRY_ENTRIES = [
        ('香港', 'HK', '🇭🇰', 'Hong Kong'), ('台湾', 'TW', '🇹🇼', 'Taiwan'),
        ('日本', 'JP', '🇯🇵', 'Japan'), ('新加坡', 'SG', '🇸🇬', 'Singapore'),
        ('美国', 'US', '🇺🇸', 'United States|USA|America'), ('韩国', 'KR', '🇰🇷', 'Korea'),
        ('英国', 'GB', '🇬🇧', 'United Kingdom|UK|Britain'), ('德国', 'DE', '🇩🇪', 'Germany'),
        ('意大利', 'IT', '🇮🇹', 'Italy'), ('法国', 'FR', '🇫🇷', 'France'), ('加拿大', 'CA', '🇨🇦', 'Canada'),
        ('澳大利亚', 'AU', '🇦🇺', 'Australia|澳洲'), ('荷兰', 'NL', '🇳🇱', 'Netherlands'),
        ('俄罗斯', 'RU', '🇷🇺', 'Russia'), ('印度', 'IN', '🇮🇳', 'India'),
        ('土耳其', 'TR', '🇹🇷', 'Turkey|Türkiye'), ('马来西亚', 'MY', '🇲🇾', 'Malaysia'),
        ('泰国', 'TH', '🇹🇭', 'Thailand'), ('越南', 'VN', '🇻🇳', 'Vietnam'),
        ('菲律宾', 'PH', '🇵🇭', 'Philippines'), ('印尼', 'ID', '🇮🇩', 'Indonesia|印度尼西亚'),
        ('瑞士', 'CH', '🇨🇭', 'Switzerland'), ('瑞典', 'SE', '🇸🇪', 'Sweden'),
        ('芬兰', 'FI', '🇫🇮', 'Finland'), ('挪威', 'NO', '🇳🇴', 'Norway'),
        ('巴西', 'BR', '🇧🇷', 'Brazil'), ('阿根廷', 'AR', '🇦🇷', 'Argentina'),
        ('墨西哥', 'MX', '🇲🇽', 'Mexico'), ('南非', 'ZA', '🇿🇦', 'South Africa'),
        ('阿联酋', 'AE', '🇦🇪', 'UAE|United Arab Emirates'), ('以色列', 'IL', '🇮🇱', 'Israel'),
        ('新西兰', 'NZ', '🇳🇿', 'New Zealand'), ('中国', 'CN', '🇨🇳', 'China')]


def country(name):
    # Group by advertised node name; this is not geolocation of the exit IP.
    name = name.split('::', 2)[-1]
    for label, code, flag, english in COUNTRY_ENTRIES:
        if label == '印度' and '印度尼西亚' in name:
            continue
        if label in name or flag in name or re.search(r'(?<![A-Za-z])(?:' + code + '|' + english + r')(?![A-Za-z])', name, re.I):
            return flag + ' ' + label
    # Handle additional flag countries without guessing from hostnames.
    flags = re.findall('[\U0001F1E6-\U0001F1FF]{2}', name)
    if flags:
        return flags[0] + ' ' + ''.join(chr(ord(c) - 0x1F1E6 + 65) for c in flags[0])
    return '🌐 其他地区'


def request_superseded(cfg):
    return '_request_id' in cfg and read_json(STATE / 'refresh.request', {}).get('id') != cfg['_request_id']


def probe(nodes, cfg, measurements=None):
    secret = secrets.token_hex(32)
    session = requests.Session()
    session.trust_env = False
    session.headers['Authorization'] = f'Bearer {secret}'
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'config.yaml'
        core_cfg = {'external-controller': '127.0.0.1:19090', 'secret': secret,
                    'log-level': 'silent', 'proxies': nodes, 'rules': ['MATCH,DIRECT']}
        path.write_text(yaml.safe_dump(core_cfg, allow_unicode=True), encoding='utf-8')
        check = subprocess.run(['mihomo', '-t', '-d', directory, '-f', str(path)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        if check.returncode:
            raise ValueError('Mihomo rejected nodes')
        process = subprocess.Popen(['mihomo', '-d', directory, '-f', str(path)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(50):
                if process.poll() is not None:
                    raise ValueError('Mihomo exited')
                try:
                    response = session.get('http://127.0.0.1:19090/version', timeout=1)
                    response.raise_for_status()
                    break
                except requests.RequestException:
                    time.sleep(0.2)
            else:
                raise ValueError('Mihomo startup timeout')

            def alive(node):
                # Any one target succeeds; retries reduce single-target false negatives.
                for url in cfg['probe_urls']:
                    if request_superseded(cfg):
                        raise InterruptedError('configuration changed')
                    try:
                        with requests.Session() as s:
                            s.trust_env = False
                            r = s.get('http://127.0.0.1:19090/proxies/' +
                                      quote(node['name'], safe='') + '/delay',
                                      headers=session.headers,
                                      params={'url': url, 'timeout': cfg['probe_timeout_ms'],
                                              'expected': '200-299'},
                                      timeout=cfg['probe_timeout_ms'] / 1000 + 3)
                            r.raise_for_status()
                            delay = r.json().get('delay', 0)
                            if 0 < delay < 65535:
                                if measurements is not None:
                                    measurements[node['name']] = delay
                                return node
                    except (requests.RequestException, ValueError, TypeError):
                        pass
                return None

            completed, available = 0, 0
            progress_lock = threading.Lock()

            def measured(node):
                nonlocal completed, available
                result = alive(node)
                with progress_lock:
                    completed += 1
                    available += result is not None
                    if completed % 10 == 0 or completed == len(nodes):
                        log_event('probe_progress', node['name'].split('::', 1)[0], done=completed, total=len(nodes), healthy=available)
                return result

            with concurrent.futures.ThreadPoolExecutor(max_workers=cfg['probe_workers']) as pool:
                return [n for n in pool.map(measured, nodes) if n is not None]
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            session.close()


def load_config():
    cfg = yaml.safe_load(CONFIG.read_text('utf-8'))
    return validate_config(cfg)


def validate_config(cfg):
    if not isinstance(cfg, dict) or not isinstance(cfg.get('sources'), list) or len(cfg['sources']) > 30:
        raise ValueError('配置格式无效，最多 30 个机场')
    if not isinstance(cfg.get('group_by_country', True), bool):
        raise ValueError('group_by_country must be boolean')
    selected = cfg.get('country_groups')
    if selected is not None and (not isinstance(selected, list) or len(selected) > 250 or
                                any(not isinstance(v, str) or len(v) > 80 or country(v) != v or
                                    v == '🌐 其他地区' for v in selected) or len(set(selected)) != len(selected)):
        raise ValueError('country_groups must contain unique country labels or be null')
    if not isinstance(cfg.get('chatgpt_group', False), bool):
        raise ValueError('chatgpt_group must be boolean')
    for key, schemes in [('public_base_url', ('https',)),
                         ('rules_fetch_proxy', ('http', 'https', 'socks5', 'socks5h'))]:
        value = cfg.get(key, '')
        if not isinstance(value, str):
            raise ValueError('invalid URL')
        if value:
            parsed = urlparse(value)
            if parsed.scheme not in schemes or not parsed.hostname or parsed.port == 0:
                raise ValueError('invalid URL')
            if key == 'public_base_url' and (parsed.username or parsed.password or parsed.query or parsed.fragment):
                raise ValueError('invalid public base URL')
    for key in ('health_interval', 'fetch_interval', 'retry_interval', 'snapshot_max_age',
                'probe_timeout_ms', 'probe_workers'):
        if type(cfg.get(key)) is not int or cfg[key] <= 0:
            raise ValueError('invalid interval/limit')
    if cfg['probe_workers'] > 16 or cfg['probe_timeout_ms'] > 30000:
        raise ValueError('probe limits too large')
    if (not isinstance(cfg.get('probe_urls'), list) or not cfg['probe_urls'] or
            any(not isinstance(u, str) or urlparse(u).scheme != 'https' or not urlparse(u).hostname for u in cfg['probe_urls'])):
        raise ValueError('HTTPS probe URLs required')
    if any(not isinstance(s, dict) or not isinstance(s.get('id'), str) for s in cfg['sources']):
        raise ValueError('invalid source')
    ids = [s['id'] for s in cfg['sources']]
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r'[a-zA-Z0-9_-]{1,40}', i) or i.lower() in ('status', 'running', 'published', 'rules-status') for i in ids):
        raise ValueError('invalid or duplicate source ids')
    rules = cfg.get('exclude_rules', [])
    if not isinstance(cfg.get('exclude_unhealthy', False), bool):
        raise ValueError('exclude_unhealthy must be boolean')
    if not isinstance(rules, list) or len(rules) > 100:
        raise ValueError('invalid exclusion rules')
    for rule in rules:
        if (not isinstance(rule, dict) or not isinstance(rule.get('enabled', True), bool) or rule.get('source_id', '') not in ['', *ids] or
                any(not isinstance(rule.get(k, ''), str) for k in ('name_contains', 'country', 'protocol')) or
                len(rule.get('name_contains', '')) > 200 or
                (rule.get('country') and (len(rule['country']) > 80 or country(rule['country']) != rule['country'])) or
                (rule.get('protocol') and not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', rule['protocol'])) or
                not any(rule.get(k, '').strip() for k in ('name_contains', 'country', 'protocol'))):
            raise ValueError('invalid exclusion rule')
    for s in cfg['sources']:
        excluded = s.get('excluded_nodes', [])
        if (not isinstance(excluded, list) or len(excluded) > 1000 or
                any(not isinstance(k, str) or not re.fullmatch(r'[a-f0-9]{64}', k) for k in excluded)):
            raise ValueError('invalid excluded nodes')
        if not isinstance(s.get('name', ''), str) or len(s.get('name', '')) > 80:
            raise ValueError('机场名称过长或格式无效')
        site = s.get('website', '')
        if not isinstance(site, str) or len(site) > 2048:
            raise ValueError('官网地址格式无效')
        if site and (urlparse(site).scheme not in ('http', 'https') or not urlparse(site).hostname or urlparse(site).username or urlparse(site).password):
            raise ValueError('官网必须为 HTTP/HTTPS 地址且不能包含账号密码')
        if not isinstance(s.get('enabled', True), bool):
            raise ValueError('enabled must be boolean')
        kind = s.get('subscription_type', 'url')
        if kind not in ('url', 'file'):
            raise ValueError('订阅类型无效')
        if kind == 'file':
            content = s.get('yaml_content')
            if not isinstance(content, str) or not content or len(content.encode('utf-8')) > LIMIT:
                raise ValueError('请选择不超过 4 MiB 的 YAML 文件')
            try:
                parse_nodes(content, s['id'])
            except Exception:
                raise ValueError('YAML 文件必须包含有效的 Clash proxies 节点列表') from None
        url = s.get('url', '')
        if not isinstance(url, str) or (kind == 'url' and s.get('enabled', True) and not url):
            raise ValueError('订阅地址必须使用 HTTPS')
        if url and (urlparse(url).scheme != 'https' or not urlparse(url).hostname or urlparse(url).port == 0):
            raise ValueError('订阅地址必须使用 HTTPS')
        proxy = s.get('fetch_proxy', '')
        if not isinstance(proxy, str) or (proxy and (urlparse(proxy).scheme not in ('http', 'https', 'socks5', 'socks5h') or not urlparse(proxy).hostname or urlparse(proxy).port == 0)):
            raise ValueError('代理地址格式无效')
        if not isinstance(s.get('headers', {}), dict) or any(not isinstance(v, str) for v in s.get('headers', {}).values()):
            raise ValueError('请求头格式无效')
    return cfg


def node_id(node):
    # Connection identity survives upstream reordering and renaming; credentials stay private.
    return hashlib.sha256(json.dumps({k: v for k, v in node.items() if k != 'name'}, sort_keys=True).encode()).hexdigest()


def rule_matches(node, source_id, rule):
    return (rule.get('enabled', True) and rule.get('source_id', '') in ('', source_id) and
            (not rule.get('name_contains') or rule['name_contains'].casefold() in node['name'].split('::', 2)[-1].casefold()) and
            (not rule.get('country') or rule['country'] == country(node['name'])) and
            (not rule.get('protocol') or rule['protocol'] == node.get('type')))


def exclusion_reason(node, source, cfg, healthy=None):
    if node_id(node) in source.get('excluded_nodes', []):
        return 'manual'
    if (cfg.get('exclude_unhealthy', False) and healthy is False or
            any(rule_matches(node, source['id'], rule) for rule in cfg.get('exclude_rules', []))):
        return 'rule'
    return None


def source_cache(source):
    cache = read_json(STATE / (source['id'] + '.json'),
                      {'nodes': [], 'fetched': 0, 'attempted': 0, 'unhealthy': True})
    if source.get('subscription_type', 'url') == 'file':
        digest = hashlib.sha256(source['yaml_content'].encode()).hexdigest()
        if cache.get('file_hash') != digest:
            nodes = parse_nodes(source['yaml_content'], source['id'])
            # New file contents must not inherit health from different connections with the same name.
            if nodes != cache.get('nodes'):
                cache.update(health={}, delays={}, checked_at=None)
            cache.update(nodes=nodes, fetched=time.time(), file_hash=digest,
                         subscription_info=None, last_error=None)
    return cache


def node_details(cfg):
    result = []
    for source in cfg['sources']:
        cache = source_cache(source)
        for node in cache.get('nodes', []):
            reason = exclusion_reason(node, source, cfg, cache.get('health', {}).get(node['name']))
            result.append({'id': node_id(node), 'source_id': source['id'],
                           'name': node['name'].split('::', 2)[-1], 'country': country(node['name']),
                           'type': node.get('type'), 'server': node.get('server'), 'port': node.get('port'),
                           'healthy': cache.get('health', {}).get(node['name']),
                           'delay_ms': cache.get('delays', {}).get(node['name']),
                           'checked_at': cache.get('checked_at'), 'excluded': reason,
                           'enabled': source.get('enabled', True)})
    return result


def cycle(cfg, force_fetch=False, check_only=False, rules_ready=True, source_id=None, publish_only=False):
    now = time.time()
    healthy, published_nodes, details = [], [], {}
    active = [s for s in cfg['sources'] if s.get('enabled', True)]
    ids = sorted(s['id'] for s in active)
    for source in active:
        if request_superseded(cfg):
            return
        sid = source['id']
        path = STATE / f'{sid}.json'
        cache = source_cache(source)
        if source.get('subscription_type') == 'file' and read_json(path, {}).get('file_hash') != cache.get('file_hash'):
            log_event('file_import', sid, count=len(cache['nodes']))
        selected = not publish_only and (source_id is None or source_id == sid)
        fingerprint = hashlib.sha256(json.dumps({k: v for k, v in source.items() if k not in ('name', 'website', 'excluded_nodes')}, sort_keys=True).encode()).hexdigest()
        changed = cache.get('source_hash') != fingerprint
        if changed:
            cache['attempted'] = 0
            cache['source_hash'] = fingerprint
        due = changed or now - cache['fetched'] >= cfg['fetch_interval'] or cache.get('unhealthy', True)
        candidate, error = None, None
        if selected and not check_only and (force_fetch or due) and (force_fetch or now - cache.get('attempted', 0) >= cfg['retry_interval']):
            cache['attempted'] = now
            try:
                log_event('file_import' if source.get('subscription_type') == 'file' else 'fetch_start', sid)
                metadata = {}
                candidate = fetch(source, metadata)
                cache.update(metadata)
                log_event('fetch_done', sid, count=len(candidate))
            except Exception as e:
                error = type(e).__name__  # Never log URL, credentials, body or raw exception.
        good, accepted, measurements, measured = [], False, {}, False
        if candidate:
            try:
                log_event('probe_start', sid, total=len(candidate))
                good = probe(candidate, cfg, measurements)
                measured = True
                # A syntactically valid new subscription replaces the old one even if temporarily offline.
                cache.update(nodes=candidate, fetched=now)
                accepted = True
            except Exception as e:
                error = type(e).__name__
        if selected and not accepted and cache['nodes']:
            try:
                measurements = {}
                log_event('probe_start', sid, total=len(cache['nodes']))
                good = probe(cache['nodes'], cfg, measurements)
                measured = True
            except Exception as e:
                error = type(e).__name__
        if measured:
            cache['unhealthy'] = not bool(good)
            alive_names = {n['name'] for n in good}
            cache['health'] = {n['name']: n['name'] in alive_names for n in cache['nodes']}
            cache.update(delays=measurements, checked_at=time.time())
        if request_superseded(cfg):
            return
        if selected or source.get('subscription_type') == 'file':
            cache['last_error'] = error
            atomic(path, json.dumps(cache, ensure_ascii=False))
        if not selected:
            good = [n for n in cache['nodes'] if cache.get('health', {}).get(n['name'])]
            error = cache.get('last_error')
        if selected or (source.get('subscription_type') == 'file' and changed):
            log_event('source_failed' if error else 'source_done', sid, cached=len(cache['nodes']), healthy=len(good), error=error)
        healthy.extend(good)
        included = [n for n in cache['nodes'] if not exclusion_reason(n, source, cfg, cache.get('health', {}).get(n['name']))]
        published_nodes.extend(included)
        details[sid] = {'healthy': len(good), 'cached': len(cache['nodes']),
                        'published': len(included) if rules_ready else 0,
                        'fetch_age_seconds': int(now - cache['fetched']) if cache['fetched'] else None,
                        'fetch_or_probe_error': error,
                        'subscription_info': cache.get('subscription_info')}
    previous = read_json(STATE / 'published.json', {})
    target = PUBLIC / 'clash.yaml'
    if published_nodes and rules_ready:
        atomic(target, yaml.safe_dump(client_config(published_nodes, cfg), allow_unicode=True, sort_keys=False))
        atomic(STATE / 'published.json', json.dumps({'time': now, 'sources': ids,
                                                    'max_age': cfg['snapshot_max_age']}))
        state = 'fresh' if healthy else 'retained'
    elif (rules_ready and not any(read_json(STATE / (s['id'] + '.json'), {}).get('nodes') for s in active) and
          not cfg.get('exclude_unhealthy', False) and not any(r.get('enabled', True) for r in cfg.get('exclude_rules', [])) and not any(s.get('excluded_nodes') for s in active) and
          previous.get('sources') == ids and target.exists() and
          now - previous.get('time', 0) <= cfg['snapshot_max_age']):
        state = 'stale_snapshot'
    else:
        target.unlink(missing_ok=True)
        state = 'unavailable'
    if not rules_ready and published_nodes:
        state = 'rules_pending'
    status = {'checked_at': now, 'state': state, 'healthy': len(healthy),
              'published': len(published_nodes) if rules_ready else 0, 'sources': details}
    atomic(STATE / 'status.json', json.dumps(status, ensure_ascii=False, indent=2))
    log_event('rules_pending' if not rules_ready else 'publish_done', published=status['published'], healthy=len(healthy))


def run_once(last_consumed):
    running = read_json(STATE / 'running.json', {})
    running.update(busy=True, started_at=time.time())
    atomic(STATE / 'running.json', json.dumps(running))
    interval, consumed = 60, last_consumed
    try:
        settings = load_config()
        interval = settings['health_interval']
        request = read_json(STATE / 'refresh.request', {})
        consumed = request.get('id')
        settings['_request_id'] = consumed
        pending = bool(consumed) and consumed != last_consumed
        source_id = request.get('source_id') if pending else None
        publish_only = request.get('publish_only', False) if pending else False
        running.update(source_id=source_id, request_id=consumed)
        atomic(STATE / 'running.json', json.dumps(running))
        log_event('publish_start' if publish_only else 'task_start', source_id)
        cached_rules = not settings.get('public_base_url') or all((PUBLIC / 'rules' / f).exists() for f in ('cn-domain.yaml', 'cn-ip.yaml'))
        rules_ready = cached_rules if publish_only and cached_rules else update_rules(settings)
        if not publish_only and any(s.get('subscription_type') == 'file' for s in settings['sources']):
            cycle(settings, publish_only=True, rules_ready=rules_ready)
        force_fetch = request.get('fetch', False) and consumed != last_consumed
        check_only = bool(consumed) and consumed != last_consumed and not request.get('fetch', False)
        cycle(settings, force_fetch=force_fetch, check_only=check_only, rules_ready=rules_ready,
              source_id=source_id, publish_only=publish_only)
        if request_superseded(settings):
            log_event('task_superseded', source_id)
            return interval, consumed
        if not rules_ready:
            raise ValueError('rules unavailable')
        running.update(last_success_at=time.time(), error=None)
        log_event('task_done', source_id)
    except Exception as e:
        running.update(last_failure_at=time.time(), error=type(e).__name__)
        log_event('task_failed', error=type(e).__name__)
    finally:
        running['busy'] = False
        atomic(STATE / 'running.json', json.dumps(running))
    return interval, consumed


if __name__ == '__main__':
    os.umask(0o022)
    log_event('service_started')
    last_consumed = None
    while True:
        interval, consumed = run_once(last_consumed)
        last_consumed = consumed
        for _ in range(interval):
            time.sleep(1)
            try:
                if read_json(STATE / 'refresh.request', {}).get('id') != consumed:
                    break
            except Exception:
                pass
