# charles

MacBook Air，Charles 本机的 macOS 开发环境。用于本地开发、命令行工具和图形桌面操作；需要 Linux 或 NVIDIA CUDA 时使用 Axiom。

## 配置

2026-09-06 在 Charles 本机读取实际运行信息。

| 项目 | 配置 |
| --- | --- |
| 计算机名 / 用户 | `charles` / `c1` |
| 机型 | MacBook Air，`Mac14,2` |
| 芯片 | Apple M2，`arm64` |
| CPU | 8 核：4 性能核 + 4 能效核 |
| 内存 | 24 GB 统一内存 |
| SSD | `APPLE SSD AP1024Z`，1.0 TB；主 APFS 容器约 994.7 GB |
| 系统 | macOS `26.6.2`，build `25G83` |
| 开发目录 | `/Users/c1/Work` |
| 系统配置目录 | `/Users/c1/Work/dotfiles`；host 入口 `hosts/charles/default.nix`，`aarch64-darwin` |
| Shell / 配置目录 | zsh；`ZDOTDIR=/Users/c1/.config/zsh` |
| Nix 环境 | Nix `2.31.2` 与 `darwin-rebuild` 可用 |

## 使用方式

在 Charles 上直接运行本地命令。基础环境核对可用：

```bash
scutil --get ComputerName
sw_vers
uname -m
```

项目通常位于 `/Users/c1/Work/<project>`。当前 shell 可解析 `direnv`、`tmux`、`node`、`deno`、`cargo`、`rustc`、`python3`、`playwright` 和 `nvim`；Emacs CLI 在 `/Applications/Emacs.app/Contents/MacOS/bin`，Doom CLI 为 `/Users/c1/.config/emacs/bin/doom`，两者当前均在有效 `PATH` 中。Doom 配置目录为 `/Users/c1/.config/doom`。

系统配置由 `/Users/c1/Work/dotfiles` 中的 Charles host 管理；该 host 当前声明 `direnv`、zsh、Git、GnuPG、tmux，以及 Node、Deno、Rust、Python 和 Playwright 开发模块。需要变更系统配置时，从该仓库按 dotfiles 的现有说明执行；本页不把源配置或当前 `darwin-rebuild` 可用性当作已完成激活的证明。

本次只核验了 Charles 本机使用方式。当前 SSH 配置没有已核验的 `charles` 主机入口，因此不提供外部 SSH 地址；从其他机器连接前需单独核对地址、账户和 host key。

来源：本机 `hostname`、`id`、`scutil`、`sw_vers`、`uname`、`sysctl`、`system_profiler`、`diskutil`、`zsh`、`command -v`；dotfiles 的 `hosts/charles/default.nix`、`flake.nix`。
