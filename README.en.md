# Mihomo Aggregate

**A self-hosted subscription aggregator and manager for Clash / Mihomo.**

[简体中文](README.md)

Fetch subscriptions from multiple providers in the background, cache each provider independently, check node availability, and publish a stable static subscription URL. Client updates download an existing configuration rather than waiting for upstream providers.

- **Live logs**: The Logs page refreshes worker/panel application container logs every 2 seconds, including provider fetches, file imports, probe progress, and publication results. Pause following or refresh manually. Shows the latest 200 entries with bounded log rotation and no subscription or node credentials.
- **File subscriptions**: Add or edit a provider using an online URL or a YAML file (up to 4 MiB, with a Clash `proxies` list). Uploaded content is stored privately; upload again to replace it. Files do not update online.
- **ChatGPT test group:** enable `chatgpt_group` in the panel to create a `ChatGPT` URL-test group probing all nodes at `https://chatgpt.com/`, selectable in `PROXY`. Defaults to `false`; a probe response does not guarantee login or chat availability.

## Features

- **Chinese and English UI:** the panel follows your browser language on first use. Switch languages in the sidebar; your choice is saved in the current browser. Dates, regions and messages follow the selected language. Subscription node names, group names and configuration values stay unchanged.
- **Independent caching:** retain the last valid nodes when an upstream request, parsing, or node configuration validation fails.
- **Keep temporarily unavailable nodes:** health checks do not remove nodes. A validated new subscription replaces its provider's previous list.
- **Configurable country groups:** use node names and flags to create country / region test groups. Choose separate groups in a settings dialog and merge remaining nodes into Other countries, or disable grouping while keeping global AUTO.
- **Traffic routing:** private networks, Chinese domains, and Chinese IP ranges connect directly; other traffic uses the proxy selection group. Chinese rules update periodically with a cached fallback.
- **Visual dashboard:** faceted crystal branding with a midnight navy and cool teal palette. Water levels represent remaining traffic. Cards show quota, expiration, total / published / available node counts, and data timestamps, with drag sorting. Click a card to show Edit, Website, single-airport Update, and Check actions within its existing dimensions.
- **Subscription management:** edit display names, websites, subscription URLs, fetch proxies, client headers, and enabled states in a dialog. Trigger updates or health checks manually.
- **Node management:** safe details and last measured delays, combined filters, bulk exclusion / restoration, persistent rules, and a bounded scrolling table.
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

The current implementation has been validated on Linux ARM64. For other architectures, check the Python and Mihomo images and validate the deployment yourself. The management interface supports Simplified Chinese and English.

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

Provider IDs cannot use the reserved names `status`, `running`, `published`, or `rules-status` (case insensitive). Enabled providers require a valid HTTPS subscription URL.

The panel reports background failures with a timestamp and a sanitized error category. The status tooltip shows the last successful and failed runs. Saving from an outdated page returns a conflict; reload before editing again to avoid overwriting another page's changes.

Missing rule files no longer stop provider fetching or node checks. The complete subscription remains unavailable until the rules have downloaded successfully, then publication resumes automatically.

For direct API access, read `config` and `version` from `GET /api/config`, then submit `{"config": <edited configuration>, "version": <version read>}` to `POST /api/config`. Successful saves return the new version; outdated versions return HTTP 409. Writes still require `X-Panel-Request: 1` and authentication when enabled.

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

## Panel and node management

### Online and file subscriptions

When adding or editing a provider, choose a subscription type:

- **Online URL**: enter an HTTPS subscription URL, with optional fetch proxy and client headers. Existing configurations without `subscription_type` keep using this mode.
- **Upload YAML file**: choose a `.yaml` or `.yml` file up to 4 MiB containing a nonempty native Clash `proxies` list, with at most 1000 standalone remote nodes. Saved nodes appear immediately without waiting for fetching or probes; the worker republishes the combined subscription from cache. Missing rules, disabled providers, and exclusions still affect publication.

File contents are stored privately inside `config/sources.yaml`, independent of the browser or original local path. Reopening the editor retains the saved file; choosing another file replaces it. Invalid or empty node lists are rejected. Files do not update online or supply quota and expiration response headers. Importing nodes does not prove connectivity; use Check Nodes or scheduled checks to measure availability.

Saving changes to one provider only updates that provider: online sources fetch and check that provider, while file sources import and republish. Other providers retain their caches. Checks using an older configuration yield to the new request; an in-flight network request may need to time out first. Update All and scheduled checks still process all enabled providers. Clients must refresh their subscriptions to receive published changes.

A file source in configuration/API payloads (`yaml_content` contains data, not a path):

```yaml
- id: uploaded_airport
  name: Uploaded provider
  enabled: true
  subscription_type: file
  file_name: nodes.yaml
  yaml_content: |
    proxies:
      - name: Example node
        type: ss
        server: proxy.example.com
        port: 443
        cipher: aes-128-gcm
        password: REPLACE_ME
```

### Live logs

Open Logs to view worker/panel application container events: queued requests, provider fetches or file imports, probe starts, progress after every 10 completed nodes (including the final partial batch), failure classes, publication results, and task completion. Each entry shows the time, service, and provider name.

Auto-refresh and follow runs every 2 seconds. Uncheck it to pause and inspect older entries, or refresh manually. Automatic log reads stop when another page is selected or the browser page is hidden. Language switching translates event messages while preserving provider names.

Events also go to container stdout and `state/worker.log` or `state/panel.log`. Each service file rotates at 1 MiB with one `.log.1` backup. The panel displays at most 200 recent entries. The API reads bounded tails of fixed files, with no arbitrary path access or Docker socket. Logs contain only event identifiers, provider IDs, counts, and exception class names; they exclude subscription URLs, node passwords, YAML contents, and raw exceptions. Docker engine diagnostics and web container access logs are outside this view.

### Subscription settings

Use the capsule switches on Settings to toggle country grouping and the ChatGPT test group. Open **Country settings** next to the grouping switch: it only lists regions cached in enabled subscriptions. Selected regions get separate groups; remaining nodes go into “🌐 其他国家”. All countries includes future regions; clearing every selection merges all nodes. Selected regions with no current nodes retain their settings but are hidden and create no empty groups.

Choose **Apply selection**, then **Save configuration** on Settings, and refresh the client subscription. Cancel, close, or Esc discards the dialog draft. `group_by_country` defaults to `true`; `chatgpt_group` defaults to `false`. Missing or `null` `country_groups` means all regions, a list selects separate groups, and `[]` merges every region:

```yaml
group_by_country: true
country_groups:
  - "🇭🇰 香港"
  - "🇯🇵 日本"
chatgpt_group: false
# Only exclude nodes whose latest check failed; unknown nodes are retained.
exclude_unhealthy: false
exclude_rules:
  - source_id: airport_a
    enabled: true # Optional; existing rules default to enabled.
    country: "🇯🇵 日本"
  - country: "🇬🇧 英国"
    protocol: vless
    enabled: false # Paused; conditions are preserved.
```

### Management API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/config` | Configuration, version, sharing URL, and available regions |
| `POST /api/config` | Save with a version; outdated versions return 409 |
| `GET /api/status` | Publication, per-airport total / published / available counts, rules, and background tasks |
| `GET /api/logs` | Latest 200 sanitized worker/panel application events, sorted by time |
| `GET /api/nodes` | Safe node details and manual / rule exclusions |
| `POST /api/refresh` | Queue an update or check, optionally for one airport |

A refresh body such as `{"fetch": true, "source_id": "airport_a"}` fetches and checks that airport. `fetch: false` only checks cached nodes; omit `source_id` for all enabled airports. Busy tasks return 409 and rapid repeats return 429. Configuration writes require the current `version` and `X-Panel-Request: 1`, plus authentication when enabled. Exclusion changes use the configuration endpoint and republish from cache.

### Navigation and node management

Navigation includes Dashboard, Nodes, Settings, and Logs. The dashboard shows airport cards and the sharing link. Update intervals and subscription options live on Settings. Node Management lists region, protocol, server address, last measured delay, and check time, with search, airport/region/protocol/status filters, and sorting. Regions come from names; delays come from the server, not the client device. Missing values are never fabricated. Node details never include passwords or private keys.

Cards distinguish total cached nodes (including excluded nodes), nodes in the last published subscription, and nodes that passed the latest server health check. Available counts include excluded nodes that passed the check; availability is not a live measurement from your device.

Drag the handle at the top right to reorder cards with a mouse or touch, or focus it and use the arrow keys. Release to save automatically; Esc cancels the drag. Saved order survives a page reload and only regenerates output without fetching or checking subscriptions.

Click an airport card to replace its information with Edit, Website, Update Subscription, and Check Nodes while keeping the name and card dimensions. Click the name again, another card, outside, or press Esc to close. Single-airport tasks leave other cached airports in the combined output. Disabled airports cannot submit tasks.

Filters only change the view. Airport, region, protocol and status support multiple selections: OR within a field, AND across fields. Status includes excluded and not excluded; use airport options marked as disabled to locate those airports. Select checkboxes to combine values. Click the heading again, click outside, or press Esc to close a filter; Clear Filters resets all selections. Exclude Filtered Results saves all matching nodes, skips already excluded nodes, and keeps original caches. Restore individual nodes or use Restore Filtered Results to clear manual exclusions within the current filters; persistent rules remain active. No matching manual exclusions disables the restore button. Without filters, it excludes all remaining nodes. Empty results disable the button. Excluding every node removes the old published subscription until nodes are restored.

The node table has a bounded height, internal scrolling, and a sticky header, keeping exclusion rules nearby. Persistent exclusion rules combine airport, region, protocol, and optional case-insensitive name keywords. Conditions within one rule use AND; matching any enabled rule excludes the node, including future nodes. At least a region, protocol, or keyword is required. For example, `{source_id: airport_a, country: "🇯🇵 日本"}` excludes Japan nodes from that airport, while `{country: "🇬🇧 英国", protocol: vless}` excludes UK VLESS nodes from all airports. Existing keyword rules remain supported.

Custom rules have a delete button and a switch; `enabled: false` pauses a rule while preserving its conditions. Existing rules default to enabled.

The first, permanent rule excludes nodes whose latest server health check failed (`exclude_unhealthy`, disabled by default); unknown nodes are retained and recovered nodes are automatically restored, subject to other exclusions.

Deleting or pausing a rule only removes that rule's exclusions. Nodes matching other enabled rules remain excluded; manual exclusions need separate restoration. Restore filtered results clears manual exclusions within the current filters; persistent rules remain in force. Manual identity follows the connection configuration through reordering or renaming; a changed endpoint or credential is a new node.

Exclusions use existing configuration version checks and regenerate output from cache without fetching upstream. Clients must refresh their subscription to receive changes.

## Development and tests

```sh
python -m pip install -r requirements.txt
ADMIN_PASSWORD=test-password-at-least-16 python -m unittest test_worker.py test_panel.py
node test_panel_ui.js
node test_panel_i18n.js
```

Tests cover cache retention, node replacement, selective country groups, cached rules, quota parsing, configuration versions and authentication, scoped tasks, measured delays, combined exclusions, and restoration. Tests also cover rule switches, failed-node exclusion and recovery, saved airport order, and per-airport publication counts. Node.js tests check multi-select filtering, bulk updates, rule preservation and sorting without npm dependencies. CI runs both suites. Live health checks require the Mihomo binary bundled in the Docker image.

| File | Responsibility |
| --- | --- |
| `worker.py` | Fetching, caching, checks, grouping, and publishing |
| `panel.py` / `panel.html` | Management API and visual interface |
| `Dockerfile` | Python and Mihomo application image |
| `Caddyfile` | Public HTTPS static delivery |
| `config/sources.example.yaml` | Provider and scheduling example |
| `.env.example` / `setup.sh` | Environment example and initialization |
| `test_worker.py` / `test_panel.py` | Automated tests |

Automated tests also cover file subscriptions, scoped saves, yielding to new requests, immediate import and cached publication, log sanitization/rotation/limits/authentication, and progress messages. The log endpoint uses the panel authentication settings. Configuration writes have a 32 MiB request limit; other write endpoints retain the 4 MiB limit.
