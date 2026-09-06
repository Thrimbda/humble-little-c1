---
name: environments
description: 当需要查询、使用或部署到 C1 的本地机器或阿里云服务器时，使用此 skill 确认机器定位、配置、SSH 入口和加密凭据的使用方式。
---

# 环境指南

## 选择机器

| 机器 | 定位 | 入口与详情 |
| --- | --- | --- |
| axiom | 日常 Linux 高性能工作站；多核计算、GPU 任务、Linux 开发 | 当前可用入口 `ssh axiom-tunnel`；[机器资料](references/axiom.md) |
| atlas | 本地 headless 服务器；目前关机 | 待用户开机后补充；[机器资料](references/atlas.md) |
| acorn | 阿里云轻量服务器；常驻服务、公网入口和 SSH 中转 | **`ssh azar`**；[机器资料](references/acorn.md) |
| charlie | Mac mini；macOS 开发与桌面操作，本次编写 skill 所在机器 | 在 Charlie 上直接执行本地命令；[机器资料](references/charlie.md) |
| charles | MacBook Air；macOS 本地开发、命令行与图形桌面操作 | 在 Charles 上直接执行本地命令；[机器资料](references/charles.md) |

只读取当前任务涉及的机器资料。`acorn` 是本指南里的机器名，`azar` 是当前本机 SSH 配置中通向它的别名；不要把 dotfiles 的 `hosts/azar/` 当作这台云服务器的配置。

## 使用方式

1. 按任务选择机器，再核对当前执行位置。`charlie` 不代表安装本 skill 的任意机器；先用 `hostname`、`uname -m` 确认。
2. SSH 优先使用资料中的已验证入口。自动执行可加 `-o BatchMode=yes -o ConnectTimeout=8`；连接后核对主机名。Axiom 的局域网直连与公网中转是两条不同路径，直连失败时使用 `axiom-tunnel`。
3. 在对应机器的项目目录内工作；系统配置由 `~/dotfiles/hosts/<机器名>/` 管理，具体操作遵循 dotfiles 仓库的现有说明。长任务使用该机器已有的 `tmux` 或服务管理方式。
4. 需要密码字段时，先读[加密凭据用法](references/secrets.md)。凭据载体是 [secrets.enc.yaml](references/secrets.enc.yaml)，解密结果直接进入消费命令的 stdin，不打印到工具输出、聊天或日志。

机器配置和连通性核验于 **2026-09-06**。硬件建议基于配置，未进行跑分；服务状态、地址和可用资源会变化，执行任务时按需复核。Atlas 暂不开机探测；Charles 已在本机完成核验，详见 [机器资料](references/charles.md)。
