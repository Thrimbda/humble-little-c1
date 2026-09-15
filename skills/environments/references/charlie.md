# charlie

Mac mini，编写本指南时运行 Codex 的本机。用于 macOS 开发、日常本地工具和需要图形桌面的操作；需要 Linux 或 NVIDIA CUDA 时使用 Axiom。

## 配置

2026-09-06 在本机读取实际运行信息。

| 项目 | 配置 |
| --- | --- |
| 计算机名 / 用户 | `charlie` / `c1` |
| 机型 | Mac mini，`Mac16,10` |
| 芯片 | Apple M4，arm64 |
| CPU | 10 核：4 个性能核 + 6 个能效核 |
| GPU | Apple M4 集成 GPU，10 核，Metal 4 |
| 内存 | 16 GB 统一内存 |
| SSD | APPLE SSD AP0256Z，系统报告 251 GB；主 APFS 容器约 245.1 GB |
| 系统 | macOS 26.6.2，build `25G83` |
| 开发目录 | `/Users/c1/Work` |
| 系统配置目录 | `/Users/c1/dotfiles`；host 入口 `hosts/charlie/default.nix`，nix-darwin / `aarch64-darwin` |
| 当前网络地址 | 采集时 `en0` 为 `192.168.10.3`；会随网络变化 |

## 连接与使用

已在 Charlie 上时直接运行本地命令：

```bash
scutil --get ComputerName
sw_vers
uname -m
```

本机 SSH 配置中的 `ssh charlie` 仍指向 `192.168.50.29:22`，与本次读取的网络地址不同，不把该别名当作当前已验证的连接方式。

从其他机器经 [Ant](ant.md) 回连的连接约定为：

```bash
ssh -J c1@106.15.156.143 -p 2222 c1@127.0.0.1
```

连接后确认返回 `charlie` / `arm64`。首次从其他客户端连接这个 host/port 时，需要登记 Charlie 的 SSH host key：ED25519 指纹为 `SHA256:jdmgytDxS3VTggdurT2JbH4TYyfZUPloev9IZDhlmwE`，公钥来源为 Charlie 的 `/etc/ssh/ssh_host_ed25519_key.pub`。不要关闭 host key 校验。

隧道由 `org.nixos.autossh-reverse-ssh` LaunchAgent 维护：Charlie 使用专用密钥 `~/.ssh/id_ed25519_charlie_tunnel`，以 `tunnel-charlie` 连接 Ant（`106.15.156.143`），转发 `127.0.0.1:2222` 到 Charlie 的 SSH。该密钥与 SOPS 使用的 `~/.ssh/id_ed25519` 不同。

可在 Charlie 查询隧道进程状态：

```bash
launchctl print "gui/$(id -u)/org.nixos.autossh-reverse-ssh"
```

经此隧道操作时，nix-darwin 激活或重载隧道可能中断 SSH。需要重载时使用本机执行环境，或确保任务可在连接中断后继续。

凭据字段为 [secrets.md](secrets.md) 中的 `charlie.sudo_password`，当前待填。SSH 公私钥继续由本机 `~/.ssh` 管理。

来源：`scutil`、`sw_vers`、`sysctl`、`system_profiler`、`diskutil`、`ipconfig`、`launchctl`；dotfiles 的 `hosts/charlie/default.nix`。
