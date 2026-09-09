# 域名资料

2026-09-09 使用本 skill 的 token 调用 Cloudflare API 查询；本次没有修改 DNS。

| 域名 | Zone ID | 状态 | DNS 查询 |
| --- | --- | --- | --- |
| `0xc1.wang` | `51e0b62129064be66905cc3272d4e786` | active | HTTP 403，未取得记录，不能解读为没有记录 |
| `0xc1.space` | `0de1dd8c02d3f55de55d72de080d4d9a` | active | 成功，分页查询共 26 条记录 |

两者的 Cloudflare Account ID 均为 `d513d71dfb51fed2c4af4fa76d30671f`，nameservers 均为 `felicity.ns.cloudflare.com`、`melinda.ns.cloudflare.com`。账户与 zone ID 是资源标识，不是凭据。

## 分工与现状

用户指定：Acorn / 阿里云相关部署使用已备案的 `0xc1.wang`；其他 cloudflared / Cloudflare Tunnel 服务使用 `0xc1.space`。备案状态来自用户说明，Cloudflare 的 active 状态不能证明备案。

`.space` 的现有记录包括：

| 主机名 | 已查到的记录 |
| --- | --- |
| `opencode-charlie.0xc1.space` | 代理 CNAME，指向 `9f33127c-3a10-47dc-9383-e27115780db8.cfargotunnel.com` |
| `opencode-axiom.0xc1.space` | 代理 CNAME，指向 `bc8b3291-de93-4f7f-807a-23f802ef021f.cfargotunnel.com` |
| `notify.0xc1.space` | 未代理 A，指向 `8.159.128.125` |

这些是部分记录示例，不是完整清单或服务健康检查。`notify.0xc1.space` 仍指向 Acorn 的公网地址，是现状与新分工的差异；本次保留，后续只有在对应服务迁移获授权时处理。

## 已核验的 token 能力

- `GET /user/tokens/verify`：成功，状态 active。
- 按域名查询两个 zone：均成功。
- `.space` DNS 记录读取：成功。
- `.wang` DNS 记录读取：HTTP 403，当前凭据访问受限，具体权限范围未能取得。
- token 策略详情读取：失败，无法确认完整权限清单。
- 未尝试创建、修改或删除记录，DNS 写权限尚未验证。后续需要 `.wang` DNS 操作时，应先取得覆盖该 zone 的相应权限凭据并重新核验。
