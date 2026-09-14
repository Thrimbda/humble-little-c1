---
name: environments
description: 当需要查询、使用或部署到 C1 的机器，或使用 C1 的 AWS、阿里云账号访问云服务时使用。
---

# 环境指南

机器连接与部署按下表选择；AWS、阿里云 API 操作读取[云服务访问](references/cloud-access.md)，其中包含账号来源、区域选择和从 SOPS 凭据调用 CLI 的方法。

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
4. 需要机器密码或云凭据时，先读[加密凭据用法](references/secrets.md)。凭据载体是 [secrets.enc.yaml](references/secrets.enc.yaml)，解密结果只经内存、管道或单次子进程环境传给消费命令，不打印到工具输出、聊天或日志。

## 构建与系统切换

- **Acorn 不做构建。**它只承担常驻服务、公网入口和 SSH 中转；不得在其上运行 Nix Build（包括 `nixos-rebuild` 的本机构建步骤）、Rust/Cargo Build，或其他会显著占用 CPU、内存的编译任务。`max-jobs = 1` 和 `cores = 1` 只是保护下限，不是允许在 Acorn 上构建的理由。
- **Nix / NixOS：Axiom 构建、目标机切换。**从持有 flake 和 SSH 配置的控制端调用 `nixos-rebuild`，以 `--build-host` 与 `--target-host` 分离构建和激活；例如切换 Acorn：

  ```bash
  nixos-rebuild switch --flake .#acorn \
    --build-host axiom-tunnel \
    --target-host azar \
    --ask-sudo-password \
    --sudo
  ```

  构建在 Axiom 上完成，`switch` 只在目标机执行。输入目标机对应的 sudo 密码；不得把密码写入命令行、日志或仓库。`--ask-sudo-password` 已隐含 `--sudo`，命令仍显式保留 `--sudo`，以明确远端激活需要 sudo。执行前确认 Axiom 能构建目标配置的 `system` / `crossSystem`；不兼容时不得退回 Acorn 本机构建。
- **Rust：只在 Axiom 编译。**包括 Cargo 触发的编译。若 Echo 需要本地可用的产物，也先在 Axiom 按 Echo 的目标平台构建，再通过既有安全传输路径发送到 Echo；不得为了方便在 Acorn 上重新编译。

机器配置和连通性核验于 **2026-09-06**。硬件建议基于配置，未进行跑分；服务状态、地址和可用资源会变化，执行任务时按需复核。Atlas 暂不开机探测；Charles 已在本机完成核验，详见 [机器资料](references/charles.md)。
