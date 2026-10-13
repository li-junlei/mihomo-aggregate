# Mihomo Aggregate

**自托管的 Clash / Mihomo 多订阅聚合与管理服务。**

[English](README.en.md)

后台定时拉取多个服务商的订阅，独立缓存节点并检测可用性，将聚合结果发布为固定的静态订阅链接。客户端更新订阅时直接下载已生成的配置，无需等待服务商响应。

- **ChatGPT 测速组**：在面板开启后生成 `ChatGPT` URL-test 组，使用 `https://chatgpt.com/` 对全部节点测速，可在 `PROXY` 中选择。`chatgpt_group` 默认 `false`；测速响应不保证登录或对话可用。

## 功能

- **独立缓存与失败降级**：上游请求、解析或节点配置校验失败时，保留该订阅上次有效的节点。
- **保留暂时失效的节点**：健康检测不删除节点；取得并验证新订阅后才替换旧列表。
- **可配置的国家分组**：根据节点名称和国旗生成国家 / 地区测速组，在设置弹窗中选择需要单独成组的地区，其余合并为“其他国家”；可关闭分组，保留全局 AUTO。
- **国内外分流**：私有网络、中国域名及中国 IP 直连，其余流量交给代理选择组。中国规则定时更新，失败保留缓存。
- **可视化管理面板**：卡片水位表示剩余流量比例；展示流量、到期日、节点状态及数据更新时间。单击卡片在原位置切换为编辑、官网、单机场更新与检查操作，尺寸不变。
- **订阅维护**：弹窗编辑显示名称、官网、订阅地址、拉取代理、客户端标识及启用状态；支持手动拉取和健康检查。
- **节点管理与排除**：详情与最近延迟、组合筛选、批量排除 / 恢复和持续排除规则；固定高度表格可内部滚动。
- **代理拉取**：支持 HTTP、HTTPS、SOCKS5 和 SOCKS5H 代理。
- **静态 HTTPS 订阅**：通过 Caddy 提供带访问令牌的固定链接，支持自动申请证书。

## 工作方式

```text
上游订阅 → 定时拉取 → 独立缓存 / Mihomo 检测 → 生成聚合配置 → Caddy → 客户端
                         ↑
                    管理面板维护
```

`worker` 负责拉取、检测、规则更新和发布；`panel` 负责配置管理；`web` 仅提供生成的订阅与规则文件。管理接口与公开订阅服务使用不同端口。

## Docker 部署

### 前置条件

- Docker Engine 与 Docker Compose 插件。
- 能访问上游订阅及规则源；受限网络可配置拉取代理。
- 如需公网 HTTPS：准备域名，将其解析到部署主机，并允许外部访问 TCP 80、443。
- 初始化脚本需要 POSIX shell 和 OpenSSL。

当前实现已在 Linux ARM64 环境验证；其他架构需确认基础镜像与 Mihomo 镜像支持，并自行验证。管理界面目前为中文。

### 1. 初始化

取得项目源码，进入项目根目录，然后执行：

```sh
sh setup.sh
```

脚本创建运行目录、从示例复制 `config/sources.yaml`，并生成 `.env` 中的订阅令牌与管理密码。已有文件不会被覆盖。

### 2. 设置环境变量

编辑 `.env`，保留脚本生成的随机凭证，并添加域名及证书联系邮箱：

```dotenv
SUB_DOMAIN=sub.example.com
ACME_EMAIL=admin@example.com
SUB_TOKEN=<生成的随机令牌>
ADMIN_PASSWORD=<生成的随机密码>
SUB_PUBLIC_URL=https://sub.example.com/<与 SUB_TOKEN 相同的令牌>/clash.yaml
PANEL_AUTH_DISABLED=false
```

| 变量 | 用途 |
| --- | --- |
| `SUB_DOMAIN` | Caddy 提供 HTTPS 的域名 |
| `ACME_EMAIL` | 自动证书申请的联系邮箱 |
| `SUB_TOKEN` | 订阅与规则文件的访问令牌 |
| `SUB_PUBLIC_URL` | 面板中展示的完整分享地址；不会自动配置反向代理 |
| `ADMIN_PASSWORD` | 管理密码，启用认证时至少 16 个字符；用户名固定为 `admin` |
| `PANEL_AUTH_DISABLED` | 仅设为 `true` 时关闭登录认证，默认 `false` |

### 3. 设置上游订阅

编辑 `config/sources.yaml`。替换示例订阅地址，关闭或删除不使用的示例项，并添加以下字段：

```yaml
public_base_url: https://sub.example.com/<与 SUB_TOKEN 相同的令牌>
rules_fetch_proxy: ""
```

`public_base_url` 是分享地址去掉 `/clash.yaml` 的部分，用于生成中国分流规则的下载地址。`rules_fetch_proxy` 可选，用于后台下载规则。

单个订阅的配置示例：

```yaml
sources:
  - id: provider_a
    name: 示例服务商
    website: https://provider.example.com
    enabled: true
    url: https://provider.example.com/subscribe?token=REPLACE_ME
    fetch_proxy: ""
    headers:
      User-Agent: clash.meta
```

`id` 应保持稳定，以便沿用缓存；`name`、`website` 可选。官网仅用于浏览器跳转，不参与订阅拉取。代理地址中的 `localhost` 指容器自身；需要访问其他容器或宿主机代理时，请使用容器可达的地址。

机场 ID 不能使用内部保留名称 `status`、`running`、`published`、`rules-status`（不区分大小写）。启用的机场必须填写有效 HTTPS 订阅地址。

### 4. 创建通用 Compose 文件

仓库的 `compose.yaml` 已提供以下通用配置。此示例使用相对挂载目录，管理端口仅绑定本机；公开 HTTPS 由仓库中的 `Caddyfile` 提供。

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

### 5. 构建并启动

```sh
docker compose -f compose.yaml build worker
docker compose -f compose.yaml up -d
```

管理入口为 `http://127.0.0.1:18081/`。远程部署时可使用 SSH 端口转发访问：

```sh
ssh -L 18081:127.0.0.1:18081 user@your-server
```

首次拉取、检测与规则下载完成后，在客户端导入：

```text
https://sub.example.com/<SUB_TOKEN>/clash.yaml
```

客户端应使用规则模式。完整订阅需要至少一个可发布节点；首次规则下载失败时应检查后台日志和网络连接。

## 面板使用

- 导航分为“仪表盘”“节点管理”“设置”；手机上导航排列在页面顶部。更新计划与订阅配置统一放在“设置”。
- 单击机场卡片后，只保留名称，原信息区域替换为“编辑机场”“访问官网”“更新订阅”“检查节点”，卡片大小不变；再次点击名称、点击其他卡片或卡片外部、按 Esc 可恢复信息。
- 单机场更新只拉取并检测该机场；单机场检查只检测该机场缓存。其他机场缓存继续合并发布。未启用机场不能提交任务。
- 编辑弹窗可管理机场名称、官网、订阅地址、代理和启用状态。已有机场 ID 只读。
- 卡片水位为剩余流量 / 总流量，数据来自上游 `subscription-userinfo` 响应头；未提供数据时不会伪造百分比。
- 未启用机场标红，并展示最后缓存的信息。关闭机场会将其节点从分享订阅排除，但不会删除缓存。
- “更新全部”触发上游拉取和节点检测；“仅检查节点”使用已有缓存。
- 流量与到期日代表最近成功获取的数据，更新时间可用于判断是否过时。
- 后台失败会显示失败时间和脱敏错误类别；状态文字的提示包含最近成功与失败时间。
- 多个页面同时编辑时，旧版本保存会被拒绝，刷新页面后再编辑，避免覆盖其他页面的修改。
- 规则文件缺失时仍会拉取和检测节点，但完整订阅暂不可用；规则下载恢复后会重新发布。

### 订阅配置与国家选择

1. 打开“设置 → 订阅配置”，通过胶囊开关启用“按国家 / 地区分组”或 ChatGPT 测速组。
2. 点击分组旁的“设置地区”，弹窗仅显示当前启用机场缓存中已有的地区。勾选的地区各自生成测速组，其余节点合并至“🌐 其他国家”。
3. “全部地区单独分组”包含以后新增的地区；全部取消时，所有节点归入其他国家。暂时无节点的已选地区会保留设置，但不显示为可选项，不生成空组。
4. 点击“应用选择”，再点击主页面“保存配置”。取消、关闭弹窗或按 Esc 不应用弹窗内的修改。最后在客户端更新订阅。

配置项 `group_by_country` 默认 `true`，`chatgpt_group` 默认 `false`。`country_groups` 缺省或为 `null` 表示全部地区单独成组，为列表时只单独分组指定地区，为 `[]` 时全部合并：

```yaml
group_by_country: true
country_groups:
  - "🇭🇰 香港"
  - "🇯🇵 日本"
chatgpt_group: false
exclude_rules:
  # 仅排除该机场的日本节点
  - source_id: airport_a
    country: "🇯🇵 日本"
  # 排除全部机场的英国 VLESS 节点
  - country: "🇬🇧 英国"
    protocol: vless
```

### 管理 API

| 接口 | 用途 |
| --- | --- |
| `GET /api/config` | 返回配置、版本、分享链接和现有可选地区 |
| `POST /api/config` | 携带版本保存配置；版本冲突返回 409 |
| `GET /api/status` | 返回发布、机场缓存、规则和后台任务状态 |
| `GET /api/nodes` | 返回安全的节点详情与手动 / 规则排除状态 |
| `POST /api/refresh` | 提交更新或检测任务，可限定机场 |

`POST /api/refresh` 的请求体为 `{"fetch": true, "source_id": "airport_a"}`：`fetch: true` 拉取并检测，`false` 只检测缓存；省略 `source_id` 时处理全部启用机场。已有任务时返回 409，短时间重复请求返回 429。配置保存、排除与恢复沿用配置接口；批量恢复只解除手动排除，命中持续规则的节点仍然排除。无可恢复节点时按钮禁用。

直接调用管理 API 时，先读取 `GET /api/config` 返回的 `config` 和 `version`，再以 `{"config": <修改后的配置>, "version": <读取的版本>}` 提交 `POST /api/config`。保存成功会返回新 `version`；版本过期返回 HTTP 409。写入仍需要 `X-Panel-Request: 1` 和启用时的认证。

## 运维

### 节点管理与排除

“节点管理”展示节点名称、机场、地区、协议、服务器地址、最近延迟和检测时间。详情接口不返回节点密码或私钥。延迟来自服务器最近一次探测，不是手机或电脑的实时延迟；缺失和失败会显示相应状态。地区仍根据名称识别，不是出口 IP 定位。

搜索及机场、地区、协议、状态筛选只改变列表。“排除当前筛选结果（数量）”保存全部匹配节点的排除标识，跨机场生效，并跳过已排除节点；不设置筛选时会排除所有未排除节点，零个匹配时禁用。“恢复当前筛选结果（数量）”批量解除筛选范围内的手动排除，跳过仅由持续规则排除的节点；持续规则始终保留。排除保留原始缓存，可逐个恢复；全部排除后撤下旧订阅，恢复节点后重新生成。

节点表格限制高度，内容在表格区域内滚动，表头固定；持续排除规则位于表格下方。

“持续排除规则”支持机场、地区、协议和名称关键词组合，至少设置地区、协议或关键词之一。同一条规则的条件需同时满足，不同规则任意命中即排除；关键词不区分大小写，后续新增的匹配节点也被排除。例如 `{source_id: airport_a, country: "🇯🇵 日本"}` 排除该机场全部日本节点；`{country: "🇬🇧 英国", protocol: vless}` 排除全部机场的英国 VLESS 节点。旧关键词规则仍然有效。删除规则解除规则排除，手动排除仍需单独恢复。手动标识基于连接配置，能承受上游排序或重命名；地址或凭证改变后视为新节点。

排除设置与现有配置一起保存，沿用版本冲突检查。后台从缓存重新发布排除结果，无需拉取上游；客户端需更新订阅才能取得新结果。

```sh
# 查看状态与后台日志
docker compose -f compose.yaml ps
docker compose -f compose.yaml logs --tail=100 worker panel

# 修改环境变量后重建面板容器
docker compose -f compose.yaml up -d panel

# 更新源码后重新构建并启动
docker compose -f compose.yaml build worker
docker compose -f compose.yaml up -d

# 停止服务
docker compose -f compose.yaml down
```

备份 `.env`、`config/`、`state/` 和 Caddy 的数据目录；这些文件可能包含凭证。`public/` 中的订阅可重新生成。恢复时保持令牌与订阅 ID 不变，可继续使用原分享地址和缓存。

## 安全与限制

- 管理接口能读取真实订阅地址并修改配置。默认启用 HTTP Basic 认证；跨网络访问时应使用 HTTPS 或 SSH 隧道。
- `PANEL_AUTH_DISABLED=true` 允许所有可达用户读取和修改配置，仅适用于可信且受隔离的网络。修改后需重建面板容器。
- 分享地址中的令牌等同于访问凭证，取得链接的人可以下载节点配置。不要在日志、截图或公开仓库中泄露。
- `.env`、真实订阅配置、节点缓存和证书状态已被 Git 忽略；公开提交前仍需检查内容。
- 上游必须提供原生 Clash / Mihomo YAML。暂不支持 Base64 节点列表、HTML 页面、自动重定向，以及依赖本地文件或外部代理链的节点。
- 有效新订阅会替换该服务商旧节点列表，即使新节点当前不可用；请求失败、无效或空订阅会保留旧缓存。
- 过期上游地址无法自动续签，需在面板更换；健康检测不能恢复已过期的凭证或耗尽的流量。
- 国家分组依据节点名称，不是出口 IP 定位。探测成功不保证所有网站均可访问。
- 国内外分流需要客户端支持相应 Mihomo 配置与规则提供器，并能访问公开规则地址。

## 开发与测试

```sh
python -m pip install -r requirements.txt
ADMIN_PASSWORD=test-password-at-least-16 python -m unittest test_worker.py test_panel.py
node test_panel_ui.js
```

测试覆盖缓存、节点替换、分组、规则、流量、配置与认证、单机场任务、延迟记录、排除及恢复。Node.js 检查界面筛选与批量排除，无需 npm 依赖。真实健康检测依赖 Docker 镜像内的 Mihomo。

| 文件 | 职责 |
| --- | --- |
| `worker.py` | 拉取、缓存、检测、分组和订阅发布 |
| `panel.py` / `panel.html` | 管理 API 与可视化界面 |
| `Dockerfile` | 构建包含 Python 与 Mihomo 的应用镜像 |
| `Caddyfile` | 公开 HTTPS 静态文件服务 |
| `config/sources.example.yaml` | 上游与调度配置示例 |
| `.env.example` / `setup.sh` | 环境变量示例与初始化 |
| `test_worker.py` / `test_panel.py` | 自动化测试 |
