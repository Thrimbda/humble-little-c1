# acorn

个人阿里云轻量服务器，承担常驻服务、公网入口和本地机器的 SSH 中转。适合部署资源需求较小的服务；重型编译、批量计算和 GPU 任务优先安排到 Axiom。

## 配置

2026-09-06 通过 **`ssh azar`** 读取实际运行信息。

| 项目 | 配置 |
| --- | --- |
| 指南中的机器名 | `acorn` |
| 当前 SSH 别名 | `azar` |
| 实际主机名 / 用户 | `aliyun-acorn` / `c1` |
| SSH 地址 | `8.159.128.125:22` |
| CPU | 2 vCPU；guest 报告 `Intel(R) Xeon(R) Platinum`，未暴露完整物理 CPU 型号 |
| 内存 | 系统可见约 1.83 GiB（`MemTotal: 1915720 kB`） |
| 磁盘 | `/dev/vda`，40 GiB；系统根分区约 40 GiB |
| 虚拟化 | KVM，x86_64 |
| 系统 | NixOS 26.05，版本 `26.05.7813.0dd31db7e6db` |
| 内核 | 6.12.87-hardened1 |
| Swap | 采集时无交换空间 |
| GPU / 带宽 / 云套餐 | 尚未核验，不据 CPU 型号推断套餐或性能保障 |
| 系统配置目录 | `/home/c1/dotfiles`；host 入口 **`hosts/acorn/default.nix`** |

## 连接与使用

```bash
ssh azar

ssh -o BatchMode=yes -o ConnectTimeout=8 azar \
  'hostname; free -h; df -h /'

# 查询当前服务，不改变运行状态
ssh azar 'systemctl list-units --type=service --state=running --no-pager'
```

本机另有 `Host acorn`，指向 `acorn.host.0xc1.space`，本次未核验该入口。操作本指南里的 Acorn 时使用已验证的 `azar`，并确认远端返回 `aliyun-acorn`。

dotfiles 中的 `hosts/azar/default.nix` 是另一份工作站配置，不能用它代表当前云服务器。`hosts/acorn/modules/platform.nix` 将 Nix 构建设为 `max-jobs = 1`、`cores = 1`；这只是保护下限。不得在 Acorn 上运行 Nix Build、Rust/Cargo Build 或其他重型编译；按[构建与系统切换](../SKILL.md#构建与系统切换)将构建交给 Axiom，Acorn 只作为目标机切换。

采集时运行的业务服务包括 Nginx、Auth Mini 及其 gateway、FRP、RustDesk signal/relay、Vaultwarden 和 `constxd`。这是运行快照；具体服务入口和配置以任务涉及的模块、服务单元为准。

Acorn 上已确认有 `127.0.0.1:2222` 和 `127.0.0.1:2223` 的监听，分别供 Charlie、Axiom 的反向 SSH 使用。运维 SSH 登录用户仍是 `c1`；Charlie 的隧道专用用户 `tunnel-charlie` 只用于端口转发，不能用作交互登录账户。

`sudo -n true` 本次未成功。需要提权时使用 [secrets.md](secrets.md) 中的 `acorn.sudo_password`；当前字段待填。

来源：本机 `ssh -G azar`；远端 `hostname`、`lscpu`、`/proc/meminfo`、`lsblk`、`systemd-detect-virt`、`systemctl`、`ss`；dotfiles 的 `hosts/acorn/default.nix`、`modules/platform.nix`、`modules/charlie-tunnel.nix`。
