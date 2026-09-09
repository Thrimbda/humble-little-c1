# 加密凭据

凭据文件为 [secrets.enc.yaml](secrets.enc.yaml)，字段为 `cloudflare.api_token`。2026-09-09 从 Charlie 的 `~/dotfiles/hosts/charlie/secrets/cloudflare-api-token.age` 解密提取 `API_TOKEN`，仅在内存和 SSH 管道中转交 SOPS 加密；已在 Charlie 解密新密文，与原 token 比对一致。

[.sops.yaml](.sops.yaml) 沿用 `environments` 的 SSH Ed25519 age recipient。匹配私钥位于 Charlie 的 `~/.ssh/id_ed25519`，不随 skill 分发。其他机器没有匹配私钥时，在 Charlie 执行 API 操作；不要为了使用 skill 复制私钥。

原 agenix 文件仍被 Charlie 的 `hosts/charlie/secrets/secrets.nix` 声明。本次只迁入 skill 使用的 SOPS 凭据，不删除该系统声明、旧密文或 `/run/agenix` 运行时文件，也不激活系统。`cloudflared-credentials.age` 是另一份 Tunnel 凭据，不是本 skill 的 API token。

## 使用

在包含 `SKILL.md` 的目录运行：

```bash
python3 scripts/cloudflare_api.py GET '/zones?name=0xc1.space'
```

脚本调用 PATH 中的 `sops`，通过子进程管道解密到内存并发送到固定的 Cloudflare API 地址；不把 token 放进命令参数、环境变量或临时明文文件。不输出 SOPS 的明文或错误原文。

Charlie 上若 PATH 中没有 SOPS，可使用现有仓库的开发环境：

```bash
ssh charlie-tunnel 'direnv exec ~/Work/humble-little-c1 python3 ~/.agents/skills/domains/scripts/cloudflare_api.py GET "/zones?name=0xc1.space"'
```

`charlie-tunnel` 是本次在 Charles 上核验的 SSH 入口；其他机器按 `environments` 查找自己的有效入口。也可在 Charlie 用 `nix shell nixpkgs#sops -c python3 ...` 提供 SOPS。

## 编辑与检查

由用户在本地编辑器中更新仓库内的密文：

```bash
SOPS_AGE_SSH_PRIVATE_KEY_FILE="$HOME/.ssh/id_ed25519" \
  sops edit references/secrets.enc.yaml
sops filestatus references/secrets.enc.yaml
```

编辑完成后更新安装副本，并重新验证 token 与目标 zone 的访问能力。不得打印 token、开启 shell trace 或把完整解密文件写回磁盘。凭据权限现状见[域名资料](domains.md)。
