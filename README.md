# Mihomo Aggregate

**自托管的 Clash / Mihomo 多订阅聚合与管理服务。**

[English](README.en.md)

后台定时拉取多个服务商的订阅，独立缓存节点并检测可用性，将聚合结果发布为固定的静态订阅链接。客户端更新订阅时直接下载已生成的配置，无需等待服务商响应。

- **实时日志**：日志页每 2 秒刷新 worker/panel 应用容器日志，展示机场拉取、文件导入、节点检测进度及发布结果；可暂停跟随、手动刷新。保留最近 200 条，日志自动轮转，不记录订阅或节点凭证。
- **文件订阅**：新增或编辑机场时选择在线 URL 或上传 YAML 文件（最大 4 MiB，须包含 Clash `proxies`）；上传内容私有持久保存，重新上传可替换，不会在线更新。
- **ChatGPT 测速组**：在面板开启后生成 `ChatGPT` URL-test 组，使用 `https://chatgpt.com/` 对全部节点测速，可在 `PROXY` 中选择。`chatgpt_group` 默认 `false`；测速响应不保证登录或对话可用。

## 功能

- **中英文界面**：管理面板支持简体中文和 English，首次按浏览器语言选择，可在侧栏切换并在当前浏览器记住偏好。日期、地区和提示同步切换；订阅节点名、分组名与配置值保持原样。
- **独立缓存与失败降级**：上游请求、解析或节点配置校验失败时，保留该订阅上次有效的节点。
- **保留暂时失效的节点**：健康检测不删除节点；取得并验证新订阅后才替换旧列表。
- **可配置的国家分组**：根据节点名称和国旗生成国家 / 地区测速组，在设置弹窗中选择需要单独成组的地区，其余合并为“其他国家”；可关闭分组，保留全局 AUTO。
- **国内外分流**：私有网络、中国域名及中国 IP 直连，其余流量交给代理选择组。中国规则定时更新，失败保留缓存。
- **可视化管理面板**：采用折面晶体图标与午夜蓝、冷青色主题；卡片青色水位表示剩余流量比例，流量与到期信息均缺失时用淡紫色水位表示可用节点占比；展示流量、到期日、总节点 / 已发布 / 可用数量及数据更新时间，支持拖动排序。单击卡片在原位置切换为编辑、官网、单机场更新与检查操作，尺寸不变。
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

当前实现已在 Linux ARM64 环境验证；其他架构需确认基础镜像与 Mihomo 镜像支持，并自行验证。管理界面支持简体中文和 English。

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

- 导航分为“仪表盘”“节点管理”“设置”“日志”；手机上导航排列在页面顶部。更新计划与订阅配置统一放在“设置”。
- 单击机场卡片后，只保留名称，原信息区域替换为“编辑机场”“访问官网”“更新订阅”“检查节点”，卡片大小不变；再次点击名称、点击其他卡片或卡片外部、按 Esc 可恢复信息。
- 卡片右上角拖动柄支持鼠标与触屏拖动排序，松开后自动保存；聚焦拖动柄后也可用方向键调整。拖动时按 Esc 可取消，刷新后保持保存的顺序。排序仅重新生成订阅，不重新拉取或检测机场。
- 卡片的“总节点”是最近拉取后缓存的全部节点（包含被排除的节点），“已发布”是最近生成订阅中该机场的节点数量，“可用”是最近服务器检测成功的节点数量。可用数量包含已排除但检测成功的节点；这些统计不代表当前设备的实时连接情况。
- 单机场更新只拉取并检测该机场；单机场检查只检测该机场缓存。其他机场缓存继续合并发布。未启用机场不能提交任务。
- 编辑弹窗可管理机场名称、官网、订阅地址、代理和启用状态。已有机场 ID 只读。
- 默认青色水位表示剩余流量 / 总流量，数据来自上游 `subscription-userinfo` 响应头。
- 仅当流量与到期信息均缺失时，卡片改用淡紫色水位表示“可用节点 / 总节点”，明确标注“可用节点占比”，并以三列大数字展示总节点、已发布、可用；隐藏缺失的流量、到期日和订阅信息更新时间。可用节点以最近服务器检测结果为准。
- 总节点为零或可用数量未知时，不显示节点水位或百分比；真实的零可用显示 0%。只要已有流量或到期信息，就保留原有展示，不以节点占比替代。
- 未启用机场标红，并展示最后缓存的信息。关闭机场会将其节点从分享订阅排除，但不会删除缓存。
- “更新全部”触发上游拉取和节点检测；“仅检查节点”使用已有缓存。
- 流量与到期日代表最近成功获取的数据，更新时间可用于判断是否过时。
- 后台失败会显示失败时间和脱敏错误类别；状态文字的提示包含最近成功与失败时间。
- 多个页面同时编辑时，旧版本保存会被拒绝，刷新页面后再编辑，避免覆盖其他页面的修改。
- 规则文件缺失时仍会拉取和检测节点，但完整订阅暂不可用；规则下载恢复后会重新发布。

### 在线与文件订阅

新增或编辑机场时，在“订阅类型”中选择：

- **在线 URL**：填写 HTTPS 订阅地址，可配置拉取代理和客户端标识。旧配置未填写 `subscription_type` 时沿用此方式。
- **上传 YAML 文件**：选择 `.yaml` 或 `.yml` 文件，最大 4 MiB，必须包含非空的原生 Clash `proxies` 列表，最多 1000 个独立远程节点。保存后节点立即出现在面板中，无需先完成联网拉取或测速；后台从缓存重新生成聚合订阅。规则缺失、机场未启用或排除条件仍会影响发布。

文件内容保存在私有 `config/sources.yaml` 中，不依赖浏览器或上传时的本机路径。重新打开编辑器可保留原文件，重新选择文件即可替换；无效或空节点文件会被拒绝。文件不会在线更新，也不提供在线订阅响应头中的流量和到期信息。导入成功不等于节点可连接，可通过“检查节点”或定时检测查看可用性。

编辑某个机场后“保存并更新”只处理该机场：在线源只拉取、检测该机场，文件源只导入并重新发布，其他机场沿用缓存。若后台仍在执行旧配置的检测，会尽快让出任务处理新配置；正在进行的网络请求可能需要等待超时。“更新全部”与定时检测仍处理全部启用机场，客户端需要更新订阅才能收到发布结果。

配置/API 中的文件源示例（`yaml_content` 是内容，不是文件路径）：

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

### 实时日志

打开“日志”，查看 worker/panel 应用容器的运行记录，包括任务提交、机场拉取/文件导入、检测开始、每完成 10 个节点的进度（末批不足 10 个也记录）、失败类别、发布结果与任务完成。每条记录显示时间、服务和机场名称。

默认每 2 秒自动刷新并跟随末尾；取消勾选可暂停刷新以查看旧记录，也可手动刷新。切换到其他页面或隐藏浏览器页面时停止自动读取日志。中英文切换同步翻译事件文案，机场名称保持原样。

日志与容器标准输出同步写入 `state/worker.log`、`state/panel.log`。每个服务文件达到 1 MiB 后轮转，保留一份 `.log.1`；面板最多显示最近 200 条。接口只读取固定日志文件的有限尾部，不读取任意路径，也不开放 Docker socket。日志仅包含事件、机场 ID、计数与异常类名，不记录订阅链接、节点密码、YAML 内容或原始异常。此入口不包含 Docker 引擎诊断与 web 容器访问日志。

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
# 仅排除最近检测失败的节点，默认关闭；未检测节点保留
exclude_unhealthy: false
exclude_rules:
  # 仅排除该机场的日本节点；enabled 缺省为 true
  - source_id: airport_a
    enabled: true
    country: "🇯🇵 日本"
  # 暂停这条规则，保留全部机场的英国 VLESS 排除条件
  - country: "🇬🇧 英国"
    protocol: vless
    enabled: false
```

### 管理 API

| 接口 | 用途 |
| --- | --- |
| `GET /api/config` | 返回配置、版本、分享链接和现有可选地区 |
| `POST /api/config` | 携带版本保存配置；版本冲突返回 409 |
| `GET /api/status` | 返回发布、各机场总节点 / 已发布 / 可用、规则和后台任务状态 |
| `GET /api/logs` | 返回按时间排序的最近 200 条脱敏 worker/panel 应用日志 |
| `GET /api/nodes` | 返回安全的节点详情与手动 / 规则排除状态 |
| `POST /api/refresh` | 提交更新或检测任务，可限定机场 |

`POST /api/refresh` 的请求体为 `{"fetch": true, "source_id": "airport_a"}`：`fetch: true` 拉取并检测，`false` 只检测缓存；省略 `source_id` 时处理全部启用机场。已有任务时返回 409，短时间重复请求返回 429。配置保存、排除与恢复沿用配置接口；批量恢复只解除手动排除，命中持续规则的节点仍然排除。无可恢复节点时按钮禁用。

直接调用管理 API 时，先读取 `GET /api/config` 返回的 `config` 和 `version`，再以 `{"config": <修改后的配置>, "version": <读取的版本>}` 提交 `POST /api/config`。保存成功会返回新 `version`；版本过期返回 HTTP 409。写入仍需要 `X-Panel-Request: 1` 和启用时的认证。

## 运维

### 节点管理与排除

“节点管理”展示节点名称、机场、地区、协议、服务器地址、最近延迟和检测时间。详情接口不返回节点密码或私钥。延迟来自服务器最近一次探测，不是手机或电脑的实时延迟；缺失和失败会显示相应状态。地区仍根据名称识别，不是出口 IP 定位。

搜索及机场、地区、协议、状态筛选只改变列表。机场、地区、协议和状态均支持复选多选，同一类选项取并集，不同类筛选取交集；状态包含“已排除 / 未排除”，未启用机场可通过带“未启用”标识的机场选项定位。点击下拉框内复选项可连续选择多个值；再次点击标题、点击外部或按 Esc 收起，“清空筛选”重置所有选项。“排除当前筛选结果（数量）”保存全部匹配节点的排除标识，跨机场生效，并跳过已排除节点；不设置筛选时会排除所有未排除节点，零个匹配时禁用。“恢复当前筛选结果（数量）”批量解除筛选范围内的手动排除，跳过仅由持续规则排除的节点；持续规则始终保留。排除保留原始缓存，可逐个恢复；全部排除后撤下旧订阅，恢复节点后重新生成。

节点表格限制高度，内容在表格区域内滚动，表头固定；持续排除规则位于表格下方。

“持续排除规则”支持机场、地区、协议和名称关键词组合，至少设置地区、协议或关键词之一。同一条规则的条件需同时满足，不同已开启的规则任意命中即排除；关键词不区分大小写，后续新增的匹配节点也被排除。例如 `{source_id: airport_a, country: "🇯🇵 日本"}` 排除该机场全部日本节点；`{country: "🇬🇧 英国", protocol: vless}` 排除全部机场的英国 VLESS 节点。旧关键词规则仍然有效。

每条自定义规则提供删除按钮与胶囊开关，关闭开关仅暂停规则（`enabled: false`），保留条件；旧规则默认开启。

首条固定规则“排除不可用节点”只能开关（`exclude_unhealthy`，默认关闭），开启后排除服务器最近检测失败的节点，未检测节点保留，恢复可用后自动恢复发布，仍需满足其他排除设置。

删除或暂停规则仅解除该条规则的排除；命中其他已开启规则的节点仍被排除，手动排除需单独恢复。手动标识基于连接配置，能承受上游排序或重命名；地址或凭证改变后视为新节点。

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
node test_panel_i18n.js
```

测试覆盖缓存、节点替换、分组、规则、流量、配置与认证、单机场任务、延迟记录、排除及恢复。测试也覆盖规则开关、不可用节点排除与恢复、机场排序持久化，以及各机场发布数量。Node.js 检查多选筛选、批量排除与恢复、规则保留和排序，无需 npm 依赖。真实健康检测依赖 Docker 镜像内的 Mihomo。

| 文件 | 职责 |
| --- | --- |
| `worker.py` | 拉取、缓存、检测、分组和订阅发布 |
| `panel.py` / `panel.html` | 管理 API 与可视化界面 |
| `Dockerfile` | 构建包含 Python 与 Mihomo 的应用镜像 |
| `Caddyfile` | 公开 HTTPS 静态文件服务 |
| `config/sources.example.yaml` | 上游与调度配置示例 |
| `.env.example` / `setup.sh` | 环境变量示例与初始化 |
| `test_worker.py` / `test_panel.py` | 自动化测试 |

文件订阅、单机场保存更新、任务让出、即时导入与缓存发布、日志脱敏/轮转/数量上限/认证以及进度文案也包含自动化测试。日志接口沿用面板的认证设置；配置写入请求上限为 32 MiB，其他写入接口仍为 4 MiB。
