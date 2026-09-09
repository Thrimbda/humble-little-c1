# Cloudflare 操作

API 基址：`https://api.cloudflare.com/client/v4`。从 skill 根目录调用 `scripts/cloudflare_api.py`；它自动读取本 skill 的 SOPS 文件，仅支持 zone / DNS 操作及 token 有效性查询。

## 查询

```bash
python3 scripts/cloudflare_api.py GET /user/tokens/verify
python3 scripts/cloudflare_api.py GET '/zones?name=0xc1.wang'
python3 scripts/cloudflare_api.py GET '/zones/51e0b62129064be66905cc3272d4e786/dns_records?per_page=100&page=1'
python3 scripts/cloudflare_api.py GET '/zones/0de1dd8c02d3f55de55d72de080d4d9a/dns_records?name=app.0xc1.space'
```

列表响应根据 `result_info.total_pages` 继续翻页。脚本每次请求一页，不自动穷尽列表。两个域名均已通过 DNS 读取验证；请求失败时不能把失败响应当成空清单。

## 写入示例

以下是后续获得具体 DNS 变更授权后的操作模板，本次初始化没有执行。先查询同名记录并保留旧值。

在 `record.json` 中写入本次目标记录，例如 Tunnel CNAME：

```json
{
  "type": "CNAME",
  "name": "app.0xc1.space",
  "content": "<实际 tunnel UUID>.cfargotunnel.com",
  "proxied": true,
  "ttl": 1
}
```

```bash
# 新建记录
python3 scripts/cloudflare_api.py POST \
  /zones/0de1dd8c02d3f55de55d72de080d4d9a/dns_records --body record.json

# 局部更新：record-id 替换为查询取得的记录 ID，patch.json 只包含本次改动字段
python3 scripts/cloudflare_api.py PATCH \
  /zones/0de1dd8c02d3f55de55d72de080d4d9a/dns_records/record-id --body patch.json
```

`.wang` 的 Acorn / 阿里云直连服务一般填写实际源站 A / AAAA 记录，地址从目标机器实时核验；不能直接沿用历史 IP。是否开启代理由具体服务决定。需要查询 zone、读取或写入 DNS 时，分别核对 Zone Read、DNS Read、DNS Write 的资源范围。

## 文档

2026-09-09 通过 Context7 查询 Cloudflare 官方文档。API 与 Tunnel 行为可能变化，后续涉及具体参数时重新查询：

- [列出 DNS 记录](https://developers.cloudflare.com/api/resources/dns/subresources/records/methods/list/)
- [创建 DNS 记录](https://developers.cloudflare.com/api/resources/dns/subresources/records/methods/create/)
- [局部更新 DNS 记录](https://developers.cloudflare.com/api/resources/dns/subresources/records/methods/edit/)
- [API 权限](https://developers.cloudflare.com/fundamentals/api/reference/permissions/)
- [Tunnel DNS 记录](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/routing-to-tunnel/dns/)
