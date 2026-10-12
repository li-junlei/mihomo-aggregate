import base64
import hmac
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
        elif self.path == '/api/config':
            self.respond(200, json.dumps({'config': worker.load_config(),
                                         'subscription_url': os.environ.get('SUB_PUBLIC_URL', '')}))
        elif self.path == '/api/status':
            self.respond(200, json.dumps({'status': worker.read_json(worker.STATE / 'status.json', {}),
                                         'running': worker.read_json(worker.STATE / 'running.json', {}),
                                         'airports': {s['id']: {'subscription_info': cache.get('subscription_info'), 'cached': len(cache.get('nodes', [])), 'healthy': sum(cache.get('health', {}).values())} for s in worker.load_config()['sources'] for cache in [worker.read_json(worker.STATE / (s['id'] + '.json'), {})]},
                                         'rules': worker.read_json(worker.STATE / 'rules-status.json', {})}))
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
            if not 0 < length <= 131072:
                raise ValueError('请求过大或为空')
            data = json.loads(self.rfile.read(length))
            with LOCK:
                if self.path == '/api/config':
                    cfg = worker.validate_config(data)
                    worker.atomic(worker.CONFIG, yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
                    os.chmod(worker.CONFIG, 0o600)
                    mode = True
                elif self.path == '/api/refresh':
                    mode = bool(data.get('fetch', False))
                else:
                    self.respond(404, '{}')
                    return
                previous = worker.read_json(worker.STATE / 'refresh.request', {})
                if self.path == '/api/refresh' and time.time() - previous.get('time', 0) < 10:
                    self.respond(429, '{"error":"请稍后再试"}')
                    return
                worker.atomic(worker.STATE / 'refresh.request', json.dumps(
                    {'id': secrets.token_hex(16), 'fetch': mode, 'time': time.time()}))
            self.respond(200, '{"ok":true}')
        except Exception:
            self.respond(400, '{"error":"配置无效：请检查机场 ID、HTTPS 地址、代理格式和时间间隔"}')


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8081), Handler).serve_forever()
