import base64
import hmac
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import yaml
import worker

AUTH_DISABLED = os.environ.get('PANEL_AUTH_DISABLED', 'false').lower() == 'true'
PASSWORD = os.environ.get('ADMIN_PASSWORD', '')
if not AUTH_DISABLED and len(PASSWORD) < 16:
    raise RuntimeError('Admin password too short')
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, code, body, kind='application/json; charset=utf-8'):
        body = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def auth(self):
        if AUTH_DISABLED:
            return True
        try:
            encoded = self.headers.get('Authorization', '').split(' ', 1)
            if encoded[0] == 'Basic':
                credentials = base64.b64decode(encoded[1], validate=True)
                if hmac.compare_digest(credentials, ('admin:' + PASSWORD).encode()):
                    return True
        except Exception:
            pass
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="Subscription Manager", charset="UTF-8"')
        self.send_header('Content-Length', '0')
        self.end_headers()
        return False

    def do_GET(self):
        if not self.auth():
            return
        if self.path == '/':
            self.respond(200, Path(__file__).with_name('panel.html').read_bytes(), 'text/html; charset=utf-8')
        elif self.path == '/panel-i18n.js':
            self.respond(200, Path(__file__).with_name('panel-i18n.js').read_bytes(), 'text/javascript; charset=utf-8')
        elif self.path == '/assets/icon-c-crystal.png':
            self.respond(200, (Path(__file__).parent / 'assets' / 'icon-c-crystal.png').read_bytes(), 'image/png')
        elif self.path == '/api/config':
            with LOCK:
                text = worker.CONFIG.read_bytes()
            self.respond(200, json.dumps({'config': worker.validate_config(yaml.safe_load(text)),
                                         'version': hashlib.sha256(text).hexdigest(),
                                         'countries': sorted({n['country'] for n in worker.node_details(worker.load_config())
                                                              if n['enabled'] and n['country'] != '🌐 其他地区'}),
                                         'subscription_url': os.environ.get('SUB_PUBLIC_URL', '')}))
        elif self.path == '/api/status':
            self.respond(200, json.dumps({'status': worker.read_json(worker.STATE / 'status.json', {}),
                                         'running': worker.read_json(worker.STATE / 'running.json', {}),
                                         'airports': {s['id']: {'subscription_info': cache.get('subscription_info'), 'cached': len(cache.get('nodes', [])), 'healthy': sum(cache.get('health', {}).values())} for s in worker.load_config()['sources'] for cache in [worker.source_cache(s)]},
                                         'rules': worker.read_json(worker.STATE / 'rules-status.json', {})}))
        elif self.path == '/api/logs':
            self.respond(200, json.dumps({'entries': worker.recent_logs()}))
        elif self.path == '/api/nodes':
            self.respond(200, json.dumps({'nodes': worker.node_details(worker.load_config())}))
        else:
            self.respond(404, '{}')

    def do_POST(self):
        if not self.auth():
            return
        # Custom header cannot be set by a cross-origin HTML form; no CORS enabled.
        if self.headers.get('X-Panel-Request') != '1' or self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self.respond(403, '{"error":"请求来源无效"}')
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= worker.LIMIT * (8 if self.path == '/api/config' else 1):
                raise ValueError('请求过大或为空')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('invalid request')
            with LOCK:
                source_id, publish_only = None, False
                if self.path == '/api/config':
                    version = hashlib.sha256(worker.CONFIG.read_bytes()).hexdigest()
                    if data.get('version') != version:
                        self.respond(409, '{"error":"配置已被其他页面修改，请刷新页面后重试"}')
                        return
                    cfg = worker.validate_config(data.get('config'))
                    old = worker.load_config()
                    old_sources = {s['id']: {k: v for k, v in s.items() if k != 'excluded_nodes'}
                                   for s in old['sources']}
                    publish_only = all(old_sources.get(s['id']) == {k: v for k, v in s.items() if k != 'excluded_nodes'}
                                       for s in cfg['sources'] if s.get('subscription_type', 'url') == 'url')
                    before = {s['id']: s for s in old['sources']}
                    after = {s['id']: s for s in cfg['sources']}
                    changed = [sid for sid in before.keys() | after.keys() if before.get(sid) != after.get(sid)]
                    if len(changed) == 1 and changed[0] in after:
                        source_id = changed[0]
                    worker.atomic(worker.CONFIG, yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
                    os.chmod(worker.CONFIG, 0o600)
                    version = hashlib.sha256(worker.CONFIG.read_bytes()).hexdigest()
                    mode = not publish_only
                elif self.path == '/api/refresh':
                    mode = data.get('fetch', False)
                    if not isinstance(mode, bool):
                        raise ValueError('invalid refresh mode')
                    source_id = data.get('source_id')
                    cfg = worker.load_config()
                    if source_id is not None and (not isinstance(source_id, str) or not any(s['id'] == source_id and s.get('enabled', True) for s in cfg['sources'])):
                        raise ValueError('unknown or disabled source')
                else:
                    self.respond(404, '{}')
                    return
                previous = worker.read_json(worker.STATE / 'refresh.request', {})
                running = worker.read_json(worker.STATE / 'running.json', {})
                if self.path == '/api/refresh' and time.time() - previous.get('time', 0) < 10:
                    self.respond(429, '{"error":"请稍后再试"}')
                    return
                if self.path == '/api/refresh' and (running.get('busy') or previous.get('id') != running.get('request_id') and previous.get('id')):
                    self.respond(409, '{"error":"后台已有任务，请等待完成后再试"}')
                    return
                worker.atomic(worker.STATE / 'refresh.request', json.dumps(
                    {'id': secrets.token_hex(16), 'fetch': mode, 'source_id': source_id,
                     'publish_only': publish_only, 'time': time.time()}))
            worker.log_event('request_queued', source_id, service='panel')
            self.respond(200, json.dumps({'ok': True, **({'version': version} if self.path == '/api/config' else {})}))
        except Exception:
            self.respond(400, '{"error":"配置无效：请检查机场 ID、HTTPS 地址、代理格式和时间间隔"}')


if __name__ == '__main__':
    worker.log_event('service_started', service='panel')
    ThreadingHTTPServer(('0.0.0.0', 8081), Handler).serve_forever()
