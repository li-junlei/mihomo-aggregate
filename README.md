# Mihomo Aggregate

**自托管的 Clash / Mihomo 多订阅聚合与管理服务。**

[English](README.en.md)

后台定时拉取多个服务商的订阅，独立缓存节点并检测可用性，将聚合结果发布为固定的静态订阅链接。客户端更新订阅时直接下载已生成的配置，无需等待服务商响应。

## 功能

- **独立缓存与失败降级**：上游请求、解析或节点配置校验失败时，保留该订阅上次有效的节点。
- **保留暂时失效的节点**：健康检测不删除节点；取得并验证新订阅后才替换旧列表。
- **国家自动分组**：根据节点名称和国旗识别国家或地区，生成“🇯🇵 日本”等 URL-test 分组及全局自动测速组。
- **国内外分流**：私有网络、中国域名及中国 IP 直连，其余流量交给代理选择组。中国规则定时更新，失败保留缓存。
- **可视化管理面板**：卡片水位表示剩余流量比例；展示流量、到期日、节点状态及数据更新时间。单击卡片展开编辑与官网访问按钮。
- **订阅维护**：弹窗编辑显示名称、官网、订阅地址、拉取代理、客户端标识及启用状态；支持手动拉取和健康检查。
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

- 单击机场卡片展开“编辑”和“访问官网”；点击其他卡片、卡片外部或按 Esc 收起。
- 编辑弹窗可管理机场名称、官网、订阅地址、代理和启用状态。已有机场 ID 只读。
- 卡片水位为剩余流量 / 总流量，数据来自上游 `subscription-userinfo` 响应头；未提供数据时不会伪造百分比。
- 未启用机场标红，并展示最后缓存的信息。关闭机场会将其节点从分享订阅排除，但不会删除缓存。
- “更新全部”触发上游拉取和节点检测；“仅检查节点”使用已有缓存。
- 流量与到期日代表最近成功获取的数据，更新时间可用于判断是否过时。

## 运维

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
```

测试覆盖缓存保留、节点替换、分组、规则缓存、流量字段解析、名称与官网校验，以及认证开关。真实健康检测依赖 Docker 镜像内的 Mihomo。

| 文件 | 职责 |
| --- | --- |
| `worker.py` | 拉取、缓存、检测、分组和订阅发布 |
| `panel.py` / `panel.html` | 管理 API 与可视化界面 |
| `Dockerfile` | 构建包含 Python 与 Mihomo 的应用镜像 |
| `Caddyfile` | 公开 HTTPS 静态文件服务 |
| `config/sources.example.yaml` | 上游与调度配置示例 |
| `.env.example` / `setup.sh` | 环境变量示例与初始化 |
| `test_worker.py` / `test_panel.py` | 自动化测试 |
