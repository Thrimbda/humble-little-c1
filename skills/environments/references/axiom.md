# axiom

日常工作的 Linux 主机，也是个人机器中执行多核计算和 NVIDIA GPU 任务的首选。桌面、开发环境和系统配置由 NixOS / dotfiles 管理。

## 配置

2026-09-06 通过 `ssh axiom-tunnel` 读取实际运行信息。

| 项目 | 配置 |
| --- | --- |
| 主机名 / 用户 | `axiom` / `c1` |
| CPU | AMD Ryzen 9 **9950X**，16 核 / 32 线程 |
| 内存 | 系统可见约 46.1 GiB（`MemTotal: 48345144 kB`）；内存条容量与频率尚未核验 |
| GPU | NVIDIA GeForce RTX 5090；显存报告 32607 MiB，32 GB 级别 |
| NVIDIA 驱动 | 595.99.02 |
| 系统盘 | KIOXIA EXCERIA G2，约 1.8 TiB（2 TB 级别）；`/dev/nvme1n1p3` 挂载 `/`，ext4 |
| 另一块磁盘 | Crucial CT1000P5SSD8，931.5 GiB（1 TB 级别）；使用前另查分区与挂载情况 |
| 系统 | NixOS 26.05，版本 `26.05.7813.0dd31db7e6db`，x86_64 |
| 内核 | 6.12.103 |
| 开发目录 | `/home/c1/Work` |
| 系统配置目录 | `/home/c1/dotfiles`；host 入口 `hosts/axiom/default.nix` |

## 连接与使用

```bash
# 经 Ant 的反向 SSH 隧道连接
ssh axiom-tunnel

# 一次性执行命令
ssh -o BatchMode=yes -o ConnectTimeout=8 axiom-tunnel \
  'hostname; nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader'
```

`axiom-tunnel` 的连接约定为 `c1@127.0.0.1:2223`，`ProxyJump c1@106.15.156.143`；反向 SSH 隧道在 [Ant](ant.md) 上监听 `127.0.0.1:2223`。`ssh axiom` 用于局域网直连 `192.168.50.88:22`。

多核编译、数据处理和 CUDA 任务优先考虑这里。先查看 `free -h`、`nvidia-smi` 和项目已有进程，再决定并行度与显存占用。当前配置不能证明某个模型或完整数据集一定能放进显存。

反向隧道由 `autossh-reverse-ssh.service` 维护。通过隧道工作时，重载系统或隧道服务可能断开当前 SSH；这类操作要在能承受断线的执行位置进行。

`sudo -n true` 本次未成功，不能假设 `c1` 免密码 sudo。需要提权时使用 [secrets.md](secrets.md) 中的 `axiom.sudo_password`；当前字段待填。

来源：远端 `lscpu`、`/proc/meminfo`、`lsblk`、`nvidia-smi`、`findmnt`、`nixos-version`；dotfiles 的 `hosts/axiom/default.nix`、`modules/workstation.nix`、`modules/autossh.nix`。
