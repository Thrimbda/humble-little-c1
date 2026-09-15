# ant

Humble Little C1 账号下的阿里云轻量服务器，作为 FRP 与全部中转流量从 Acorn 迁出的目标。按 C1 于 **2026-09-15** 提供的套餐信息，Ant 流量不限量，适合承担原来由按流量计费的 Acorn 承载的中转职责。

目前已部署 Acorn 同源的 NixOS 基础环境，**FRP 和业务服务尚未迁入**。新增 FRP／中转部署优先安排到 Ant；Acorn 的其他常驻应用继续保留原位。

## 配置

2026-09-15 通过 **`ssh c1@106.15.156.143`** 读取实际运行信息；云资源标识来自当日部署记录。

| 项目 | 配置 |
| --- | --- |
| 指南中的机器名 | `ant` |
| SSH 入口 | `ssh c1@106.15.156.143`，使用 IP 直连 |
| 实际主机名 / 用户 | `ant` / `c1` |
| SSH 地址 | `106.15.156.143:22` |
| 云账号 / 区域 | `humble-little-c1` / `cn-shanghai`（上海） |
| 云产品 / 实例 ID | 轻量应用服务器（Simple Application Server / `swas-open`）/ `3943f1fc74954c79a53036d6f9adc6db` |
| CPU | 2 vCPU；guest 报告 `Intel(R) Xeon(R) Platinum`，未暴露完整物理 CPU 型号 |
| 内存 | 套餐 2 GB；系统可见约 1.83 GiB（`MemTotal: 1917636 kB`） |
| 磁盘 | `/dev/vda`，40 GiB；根分区约 39.7 GiB，ext4；UEFI 启动 |
| 虚拟化 | KVM，x86_64 |
| 系统 | NixOS 26.05，版本 `26.05.7813.0dd31db7e6db` |
| 内核 | 6.12.103 |
| Swap | 采集时无交换空间 |
| 内网地址 | `172.24.51.41`，接口 `ens5`，DHCP |
| 流量 / 带宽 | 流量不限量（C1 提供）；带宽上限未核验，不据此推断传输速度 |
| 系统配置目录 | `/home/c1/dotfiles`；host 入口 **`hosts/ant/default.nix`** |

## 连接与使用

```bash
ssh c1@106.15.156.143

ssh -o BatchMode=yes -o ConnectTimeout=8 c1@106.15.156.143 \
  'hostname; free -h; df -h /'

# 查询当前服务，不改变运行状态
ssh c1@106.15.156.143 \
  'systemctl list-units --type=service --state=running --no-pager'
```

连接后确认主机名为 `ant`。2026-09-15 核验的 ED25519 主机公钥指纹为 `SHA256:7tZaBdB/DgeC1X31zy6F45KDTPH7iYLGTjAAfl2E+vY`。

`c1` 使用现有 SSH 公钥登录，密码登录与 root SSH 登录已禁用；`sudo -n true` 已成功，无需新增 sudo 密码或复制 Acorn 的应用凭据。云 API 按[云服务访问](cloud-access.md)选择 `--account humble-little-c1 --region cn-shanghai`，使用 `swas-open` 操作该轻量服务器。

采集时 SSH、Fail2ban 和 vnStat 等基础服务运行正常，没有失败的 systemd 单元。FRP、Nginx、Docker、Vaultwarden 等业务服务未启用，主机防火墙仅放行入站 TCP 22。FRP 迁移需要另行部署对应配置、开放所需端口并验证客户端；现有 Acorn 中转与 SSH 入口仍按原配置使用。

Ant 不做 Nix Build、Rust/Cargo Build 或其他重型编译；按[构建与系统切换](../SKILL.md#构建与系统切换)在 Axiom 构建、Ant 激活。dotfiles 的 flake 为 `.#ant`，基础镜像入口为 `hosts/ant/image.nix`。

## 镜像与恢复

2026-09-15 已保留原系统恢复快照 `s-uf6e4vphwx8b4tr5nj02`，并创建可用的轻量自定义镜像 `nixos-ant-20260915`（`m-uf61yhkxw7q61knq4il8`）。镜像包含基础系统，未包含后续 FRP 部署。

系统通过直接写入磁盘安装；阿里云控制台可能仍显示原始镜像为 Alibaba Cloud Linux，实际运行系统以 `nixos-version` 为准。完整构建、安装、快照和校验记录见 [dotfiles 的 Ant 部署记录](https://github.com/Thrimbda/dotfiles/blob/master/hosts/ant/README.md)。

来源：远端 `hostname`、`lscpu`、`/proc/meminfo`、`lsblk`、`nixos-version`、`systemctl`、`ss`、`sudo -n true`；dotfiles 的 `hosts/ant/` 与 [PR #233](https://github.com/Thrimbda/dotfiles/pull/233)；C1 于 2026-09-15 确认的流量计费信息及职责调整方向。
