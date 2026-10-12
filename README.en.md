# Mihomo Aggregate

**A self-hosted subscription aggregator and manager for Clash / Mihomo.**

[简体中文](README.md)

Fetch subscriptions from multiple providers in the background, cache each provider independently, check node availability, and publish a stable static subscription URL. Client updates download an existing configuration rather than waiting for upstream providers.

## Features

- **Independent caching:** retain the last valid nodes when an upstream request, parsing, or node configuration validation fails.
- **Keep temporarily unavailable nodes:** health checks do not remove nodes. A validated new subscription replaces its provider's previous list.
- **Country groups:** identify countries and regions from node names and flags, then create URL-test groups such as “🇯🇵 日本” and a global automatic selection group.
- **Traffic routing:** private networks, Chinese domains, and Chinese IP ranges connect directly; other traffic uses the proxy selection group. Chinese rules update periodically with a cached fallback.
- **Visual dashboard:** water levels represent remaining traffic. Cards show quota, expiration, node availability, and data timestamps. Click a card to reveal editing and website actions.
- **Subscription management:** edit display names, websites, subscription URLs, fetch proxies, client headers, and enabled states in a dialog. Trigger updates or health checks manually.
- **Proxy fetching:** supports HTTP, HTTPS, SOCKS5, and SOCKS5H proxies.
- **Static HTTPS delivery:** Caddy serves token-protected subscriptions and can obtain certificates automatically.

## Architecture

```text
Upstream → Scheduled fetch → Per-provider cache / Mihomo checks → Static configuration → Caddy → Client
                                       ↑
                                 Management panel
```

The `worker` fetches subscriptions, checks nodes, updates rules, and publishes files. The `panel` manages configuration. The `web` service only serves generated subscriptions and rules. Management and public delivery use separate ports.

## Docker deployment

### Requirements

- Docker Engine and the Docker Compose plugin.
- Connectivity to upstream subscriptions and rule sources, optionally through a fetch proxy.
- For public HTTPS: a domain pointing to the deployment host and externally accessible TCP ports 80 and 443.
- A POSIX shell and OpenSSL for initialization.

The current implementation has been validated on Linux ARM64. For other architectures, check the Python and Mihomo images and validate the deployment yourself. The management interface is currently in Chinese.

### 1. Initialize

Obtain the source, enter the project root, and run:

```sh
sh setup.sh
```

This creates runtime directories, copies the example to `config/sources.yaml`, and generates a subscription token and admin password in `.env`. Existing files are preserved.

### 2. Configure environment variables

Edit `.env`, retain the generated random credentials, and add your domain and certificate contact email:

```dotenv
SUB_DOMAIN=sub.example.com
ACME_EMAIL=admin@example.com
SUB_TOKEN=<generated random token>
ADMIN_PASSWORD=<generated random password>
SUB_PUBLIC_URL=https://sub.example.com/<same token as SUB_TOKEN>/clash.yaml
PANEL_AUTH_DISABLED=false
```

| Variable | Purpose |
| --- | --- |
| `SUB_DOMAIN` | Domain served over HTTPS by Caddy |
| `ACME_EMAIL` | Contact email for automatic certificate issuance |
| `SUB_TOKEN` | Access token for subscriptions and rule files |
| `SUB_PUBLIC_URL` | Full sharing URL displayed in the panel; does not configure a reverse proxy |
| `ADMIN_PASSWORD` | At least 16 characters when authentication is enabled; username is `admin` |
| `PANEL_AUTH_DISABLED` | Only `true` disables authentication; defaults to `false` |

### 3. Configure providers

Edit `config/sources.yaml`. Replace example URLs, disable or remove unused examples, and add:

```yaml
public_base_url: https://sub.example.com/<same token as SUB_TOKEN>
rules_fetch_proxy: ""
```

`public_base_url` is the sharing URL without `/clash.yaml`; it determines the rule download URLs in the generated configuration. The optional `rules_fetch_proxy` is used for background rule downloads.

Example provider:

```yaml
sources:
  - id: provider_a
    name: Example Provider
    website: https://provider.example.com
    enabled: true
    url: https://provider.example.com/subscribe?token=REPLACE_ME
    fetch_proxy: ""
    headers:
      User-Agent: clash.meta
```

Keep `id` stable to retain the cache association. `name` and `website` are optional. Websites are only opened in the browser, not used for fetching subscriptions. In a proxy URL, `localhost` means the container itself; use an address reachable from the container for a host or another container's proxy.

### 4. Create a portable Compose file

The included `compose.yaml` provides the following portable configuration. It uses relative bind mounts and exposes the management port only on loopback. The repository's `Caddyfile` handles public HTTPS.

```yaml
name: mihomo-aggregate
services:
  worker:
    build: .
    image: local/mihomo-aggregate:1
    restart: unless-stopped
    init: true
    volumes:
      - ./config:/config:ro
      - ./state:/state
      - ./public:/public
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
  panel:
    image: local/mihomo-aggregate:1
    command: [python, panel.py]
    restart: unless-stopped
    environment:
      ADMIN_PASSWORD: ${ADMIN_PASSWORD:-}
      PANEL_AUTH_DISABLED: ${PANEL_AUTH_DISABLED:-false}
      SUB_PUBLIC_URL: ${SUB_PUBLIC_URL}
    ports:
      - "127.0.0.1:18081:8081"
    volumes:
      - ./config:/config
      - ./state:/state
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
  web:
    image: caddy:2.11.7-alpine
    restart: unless-stopped
    environment:
      SUB_DOMAIN: ${SUB_DOMAIN}
      ACME_EMAIL: ${ACME_EMAIL}
      SUB_TOKEN: ${SUB_TOKEN}
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - ./public:/srv:ro
      - ./caddy-data:/data
      - ./caddy-config:/config
    security_opt: [no-new-privileges:true]

```

### 5. Build and start

```sh
docker compose -f compose.yaml build worker
docker compose -f compose.yaml up -d
```

Open `http://127.0.0.1:18081/` for management. For a remote deployment, use SSH port forwarding:

```sh
ssh -L 18081:127.0.0.1:18081 user@your-server
```

Once the first fetch, checks, and rule downloads complete, import this URL into your client:

```text
https://sub.example.com/<SUB_TOKEN>/clash.yaml
```

Use rule mode in the client. Publishing requires at least one cached node. If the initial rule download fails, check worker logs and network connectivity.

## Using the dashboard

- Click a card to reveal Edit and Visit Website. Click another card, click outside, or press Esc to collapse it.
- Edit provider names, websites, URLs, proxies, and enabled states in the dialog. Existing IDs are read-only.
- Water levels equal remaining traffic divided by total quota, using the upstream `subscription-userinfo` response header. Missing data is never represented as a fabricated percentage.
- Disabled providers are marked red and retain their last cached information. Disabling removes their nodes from the shared subscription without deleting the cache.
- Update All fetches subscriptions and checks nodes. Check Nodes Only uses existing caches.
- Quota and expiration values reflect the latest successful fetch, not a live account balance; consult their timestamps.

## Operations

```sh
# Inspect services and logs
docker compose -f compose.yaml ps
docker compose -f compose.yaml logs --tail=100 worker panel

# Recreate the panel after changing environment variables
docker compose -f compose.yaml up -d panel

# Rebuild after updating source code
docker compose -f compose.yaml build worker
docker compose -f compose.yaml up -d

# Stop services
docker compose -f compose.yaml down
```

Back up `.env`, `config/`, `state/`, and Caddy data directories securely; they may contain credentials. Files in `public/` can be regenerated. Retain tokens and provider IDs when restoring to preserve sharing URLs and cache associations.

## Security and limitations

- The management API can read subscription credentials and modify configuration. HTTP Basic authentication is enabled by default; use HTTPS or an SSH tunnel across networks.
- `PANEL_AUTH_DISABLED=true` lets anyone who can reach the panel read and modify configuration. Use it only in trusted, isolated networks and recreate the panel after changing it.
- The sharing token is a credential: anyone holding the URL can download node configurations. Keep it out of public logs, screenshots, and repositories.
- Git ignores `.env`, live subscription configuration, caches, and certificate state. Still review files before public commits.
- Upstreams must return native Clash / Mihomo YAML. Base64 node lists, HTML responses, automatic redirects, and nodes dependent on local files or external proxy chains are unsupported.
- A validated new subscription replaces old nodes even if the new nodes are currently unavailable. Failed requests and invalid or empty subscriptions retain the old cache.
- Expired upstream URLs cannot be renewed automatically; replace them in the panel. Health checks cannot repair expired credentials or exhausted quota.
- Country grouping uses advertised names, not exit-IP geolocation. A successful probe does not guarantee access to every website.
- Routing requires a compatible Mihomo client with rule-provider support and access to the public rule URLs.

## Development and tests

```sh
python -m pip install -r requirements.txt
ADMIN_PASSWORD=test-password-at-least-16 python -m unittest test_worker.py test_panel.py
```

Tests cover cache retention, node replacement, country groups, cached rules, quota parsing, display-name and website validation, and authentication modes. Live health checks require the Mihomo binary bundled in the Docker image.

| File | Responsibility |
| --- | --- |
| `worker.py` | Fetching, caching, checks, grouping, and publishing |
| `panel.py` / `panel.html` | Management API and visual interface |
| `Dockerfile` | Python and Mihomo application image |
| `Caddyfile` | Public HTTPS static delivery |
| `config/sources.example.yaml` | Provider and scheduling example |
| `.env.example` / `setup.sh` | Environment example and initialization |
| `test_worker.py` / `test_panel.py` | Automated tests |
