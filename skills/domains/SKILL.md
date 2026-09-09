---
name: domains
description: 查询和配置 C1 的 0xc1.wang、0xc1.space 域名及 Cloudflare DNS；按 Acorn/阿里云与 cloudflared 服务的分工选择域名，并使用 SOPS 中的 Cloudflare token。
---

# 域名

英文名：`domains`。

## 选择域名

| 部署用途 | 域名 | 约定 |
| --- | --- | --- |
| Acorn / 阿里云机器相关部署 | `0xc1.wang` | 用户确认已在国内备案，相关部署统一使用此域名 |
| 其他通过 cloudflared / Cloudflare Tunnel 暴露的服务 | `0xc1.space` | 用于这类服务的子域名与 Tunnel 路由 |

先按承载机器判断：Acorn / 阿里云相关部署使用 `.wang`，即使接入方式涉及 Tunnel。备案信息来自用户于 2026-09-09 的说明，未独立查询备案系统。

现有记录可能早于这个分工；不要因初始化或查询而批量迁移它们。机器入口、服务部署和系统配置位置使用 `environments` skill；本 skill 维护域名选择、Cloudflare 资源与 DNS 操作。

## 配置流程

1. 根据部署用途选择根域名，确定完整主机名和目标服务。读取[域名资料](references/domains.md)，操作前通过 API 复核 zone 与同名 DNS 记录。
2. 按[加密凭据用法](references/secrets.md)使用 SOPS token。当前 token 已验证有效，能读取 `.space` 的 DNS；`.wang` 的 DNS 读取返回 403。不能据此认定拥有 DNS 写权限，也不能把权限不足的 `.wang` 部署改放 `.space`。
3. 选择记录：直连源站使用 A / AAAA；Tunnel 使用指向 `<tunnel-uuid>.cfargotunnel.com` 的 CNAME，开启代理、TTL 使用自动值 `1`。Tunnel 还需要匹配主机名的 ingress 和可用源站，DNS 记录本身不完成服务部署。
4. 列出同名的全部记录，核对类型、目标、代理状态和 TTL，避免 CNAME 与 A / AAAA 等记录冲突。新增使用 POST，局部更新指定记录使用 PATCH；保留不在本次范围内的记录与字段。直连源站是否代理按服务协议和既有部署要求决定。
5. 在用户已授权的变更范围内执行；仅查询、初始化 skill 或取得 token 不代表授权修改线上 DNS。权限不足时报告具体请求与错误，不尝试扩大 token 权限。
6. 写入后重新 GET 核对记录，并按服务类型验证 DNS、TLS 和实际入口。记录修改前的值以便回退；Cloudflare API 成功不等于源站或 Tunnel 已可用。

API 操作和示例见[Cloudflare 操作](references/cloudflare.md)。配置快照注明核验日期，后续操作以实时查询为准。
