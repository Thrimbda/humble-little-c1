# 域名资料

2026-09-09 使用本 skill 的 SOPS token 完整分页查询 Cloudflare DNS API；共 38 条记录，本次未修改 DNS。以下统计按 DNS 记录条数计算，不按唯一主机名计算。

## 域名与用途

| 域名 | Zone ID | 用途 | 记录数 |
| --- | --- | --- | --- |
| `0xc1.wang` | `51e0b62129064be66905cc3272d4e786` | Acorn / 阿里云相关部署，用户确认已备案 | 12 |
| `0xc1.space` | `0de1dd8c02d3f55de55d72de080d4d9a` | 其他 cloudflared / Cloudflare Tunnel 服务 | 26 |

两个 zone 的状态均为 active，Cloudflare Account ID 均为 `d513d71dfb51fed2c4af4fa76d30671f`，nameservers 均为 `felicity.ns.cloudflare.com`、`melinda.ns.cloudflare.com`。备案信息来自用户说明，active 不代表备案核验。

## 去向统计

| DNS 目标类别 | `.wang` | `.space` |
| --- | ---: | ---: |
| Acorn 公网地址 `8.159.128.125`（A） | 12 | 1 |
| Cloudflare Tunnel（CNAME → `*.cfargotunnel.com`） | 0 | 9 |
| 其他 IP（A） | 0 | 3 |
| GitHub Pages 目标（CNAME → `thrimbda.github.io`） | 0 | 2 |
| MX / NS / TXT | 0 | 11 |
| **总计** | **12** | **26** |

`ssh azar` 当前连接 `8.159.128.125`，返回主机名 `aliyun-acorn`。这里只据 API 中的目标判断入口去向，不把 DNS 记录等同于服务健康或最终进程所在机器。开启 Cloudflare 代理的 A 记录仍以 Acorn 为源站，不属于 Tunnel。

## `.wang`：全部指向 Acorn

12 条均为 A 记录、目标 `8.159.128.125`，其中 10 条直接解析，2 条开启 Cloudflare 代理。

| 主机名 | Cloudflare 代理 | TTL（秒；1 为自动） |
| --- | --- | ---: |
| `1ex-portfolio.0xc1.wang` | 关闭 | 1 |
| `auth.0xc1.wang` | 关闭 | 1 |
| `auth-gateway.0xc1.wang` | 关闭 | 1 |
| `constx.0xc1.wang` | 关闭 | 1 |
| `cybion.0xc1.wang` | 关闭 | 300 |
| `frps-acorn.0xc1.wang` | 关闭 | 1 |
| `notify.0xc1.wang` | 关闭 | 60 |
| `opencode-axiom.0xc1.wang` | 开启 | 1 |
| `pi-axiom.0xc1.wang` | 关闭 | 1 |
| `rustdesk.0xc1.wang` | 关闭 | 1 |
| `status-axiom.0xc1.wang` | 关闭 | 1 |
| `vault.0xc1.wang` | 开启 | 1 |

## `.space`：Tunnel 与其他入口

9 条 Tunnel CNAME 均开启代理、TTL 为自动，分布在 6 个不同的 Tunnel UUID。DNS 目标不能单独证明 connector 正在线上。

| 主机名 | Tunnel UUID（目标后缀 `.cfargotunnel.com`） |
| --- | --- |
| `abc-imbalance.0xc1.space` | `5f128e39-a3eb-40ee-876f-ad8c34264e20` |
| `axiom-opencode.0xc1.space` | `bc8b3291-de93-4f7f-807a-23f802ef021f` |
| `constx-charlie.0xc1.space` | `9f33127c-3a10-47dc-9383-e27115780db8` |
| `facility-assets-api.0xc1.space` | `f735b2fa-8f12-4091-9af0-7a804f1074e2` |
| `legionmind.0xc1.space` | `fb1dab94-0432-4db7-b6bc-d66201e7da74` |
| `opencode-axiom.0xc1.space` | `bc8b3291-de93-4f7f-807a-23f802ef021f` |
| `opencode-charlie.0xc1.space` | `9f33127c-3a10-47dc-9383-e27115780db8` |
| `status-axiom.0xc1.space` | `bc8b3291-de93-4f7f-807a-23f802ef021f` |
| `stock-workbench.0xc1.space` | `bb0de7bf-f4f8-44ff-ba41-3d83a0a4eb12` |

其他 6 条服务入口记录：

| 主机名 | 类型 | 目标 | 代理 | TTL |
| --- | --- | --- | --- | ---: |
| `acorn.host.0xc1.space` | A | `20.205.177.226` | 关闭 | 1 |
| `notify.0xc1.space` | A | `8.159.128.125` | 关闭 | 300 |
| `stock.0xc1.space` | A | `76.76.21.21` | 关闭 | 1 |
| `vault.0xc1.space` | A | `20.205.177.226` | 关闭 | 1 |
| `0xc1.space` | CNAME | `thrimbda.github.io` | 开启 | 1 |
| `www.0xc1.space` | CNAME | `thrimbda.github.io` | 开启 | 1 |

`notify.0xc1.space` 仍指向 Acorn，是现状与新分工的差异，未在本次迁移。`acorn.host.0xc1.space` 虽然带有 acorn 名称，实际指向 `20.205.177.226`，不能当作当前阿里云 Acorn 的地址。其他历史 IP 的归属未独立核验。

其余 11 条为 6 条 MX、2 条 NS、3 条 TXT：

| 主机名 | 类型 | 目标或说明 |
| --- | --- | --- |
| `0xc1.space` | MX | eforward3.registrar-servers.com |
| `0xc1.space` | MX | eforward2.registrar-servers.com |
| `0xc1.space` | MX | eforward1.registrar-servers.com |
| `0xc1.space` | MX | eforward4.registrar-servers.com |
| `0xc1.space` | MX | eforward5.registrar-servers.com |
| `send.0xc1.space` | MX | feedback-smtp.ap-northeast-1.amazonses.com |
| `0xc1.space` | NS | dns2.registrar-servers.com |
| `0xc1.space` | NS | dns1.registrar-servers.com |
| `0xc1.space` | TXT | 文本记录；未在本资料复制内容 |
| `resend._domainkey.0xc1.space` | TXT | 文本记录；未在本资料复制内容 |
| `send.0xc1.space` | TXT | 文本记录；未在本资料复制内容 |

上表 NS 是 DNS 记录列表中返回的记录；zone 的分配 nameservers 见前文。清单用于查询与去向判断，不是可直接导入的完整恢复备份。

## 凭据核验

当前凭据来源为 Charlie 的 `~/dotfiles/hosts/acorn/secrets/cloudflare-dns.env.age`，字段 `CF_DNS_API_TOKEN`。token 状态 active，两个 zone 的 DNS 都已完整读取。完整 token 策略详情接口不可读；本次未进行线上写入，因此不声称所有写权限均已验证。

操作前重新查询当前记录与目标服务状态；不要因本快照或域名分工自动迁移现有记录。
