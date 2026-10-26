# 运行与协议

## 现场选择

先确认 `pi --version`、`pi --help`、项目指令和现有开发环境。不同发行版可能同名；核实安装包来源及当前版本文档，不能套用另一 fork 的参数。需要查 CLI 文档时遵循宿主的文档检索约定。

| 现场 | 选择 |
| --- | --- |
| 项目有已验证的 dev shell / 容器 | 在其中启动 runner，使 pi 和工具继承该环境 |
| NixOS，缺工具或遇到 ELF loader 问题 | 优先已有 flake/devShell；必要时用合适的 `nix develop` / `nix shell`，不假定 apt、FHS 路径或预编译二进制可用 |
| 其他 Linux / macOS | 使用已有工具链；不为执行这个 skill 安装 Nix |
| Windows | 流程适用；附带 runner 不支持原生 Windows，需要验证 WSL 或适配 Job Object 等机制 |
| 必须约束内存或可能产生脱离进程组的子进程 | 使用已验证的 cgroup / 容器 / 作业管理器；显式配置和记录，不能把进程组当作资源或安全隔离 |

systemd 是独立能力，不等同于 NixOS。有 user manager 时可用唯一命名的 transient service 包住整个 runner，按当前宿主文档配置 MemoryMax、KillMode 等；否则选择可用的容器/作业管理器。未设置上限时如实记录，不能声称受到内存保护。禁止无关的系统级配置变更。

## 一轮执行

附带脚本只依赖 POSIX 和 Python 3.9+ 标准库。先把提示写成 UTF-8 文件，路径均替换为现场确认的绝对路径：

```bash
python3 /path/to/pi-supervision/scripts/run_round.py \
  --cwd /path/to/project \
  --run-dir /path/to/private-task-records \
  --round 01 \
  --prompt /path/to/round-01-prompt.md \
  --provider deepseek --model deepseek-flash \
  --tools read,grep,find,ls \
  --timeout-seconds 600
```

模型名只是示例，以用户选择和已配置的 provider/model 为准。`--tools none` 禁用工具；默认 `read,bash,edit,write` 适合已获授权的实现。提供 bash 就拥有其执行能力，不能把提示中的“只读”当强制保护。

脚本使用 `--no-extensions --no-skills --no-prompt-templates`；本机支持时附加 `--no-mcp`，使加载的额外能力明确。需要扩展能力时先审查并适配 runner，而不是静默启用。项目指令是否被 pi 加载取决于当前 pi 的 trust 设置；监督者仍须读取并在 prompt 中传达适用规则。

下一轮改 `--round 02` 和 prompt，其余任务参数相同。默认 session 是 run-dir 下的 `session.jsonl`；也可指定绝对 `--session`。同一 session 使用 flock 防止本脚本并发写入；它不能阻止绕过 runner 的外部 pi 进程，所以启动前仍需核对现场。

## 保存和完成判定

| 文件 | 内容 |
| --- | --- |
| `prompt.md` | 本轮实际发送的完整提示 |
| `events.jsonl` | stdout 原始字节，不将 stderr 混入 |
| `output.md` | 每个已结束 assistant 消息的文字，包括中间说明；不重复拼接 delta |
| `live.txt` | 流式文字 delta，保留未结束消息的部分文字 |
| `stderr.log` | 独立诊断输出 |
| `meta.json` | 参数、版本、时间、执行状态、消息 stopReason、异常和工具失败 |
| `review.md` | 监督者另外写的审查与验收结论 |

日志可能包含源码和工具输出，目录采用私有权限。密钥通过已有认证环境注入，不能放进 prompt、命令参数或提交的日志中。原始记录留在本机，公开前审查并制作脱敏副本。

runner 按 **LF** 拆 JSONL，不把 JSON 字符串内的 Unicode 行分隔符当边界。持续消费 stdout 防止缓冲区堵塞。`message_update` 的 `text_delta` 用于实时显示，`message_end.message` 是保存完整消息的依据。`thinking` 和工具调用内容保留在原始事件中，不混作文字回答。

本实现以 earendil-works/pi-coding-agent **1.3.0** 的协议验证：必须收到未 aborted 的 `agent_settled`，最终 assistant 的 stopReason 为 `stop`，且进程为零退出、流无损坏，才标记 `execution_complete`。仅收到 `agent_end`、只有 toolUse、截断 JSON、缺少终态均失败。版本不兼容时先 smoke 并适配/验证，不能去掉完成检查来“修好”报错。

之前的 error 可被自动恢复；最终成功则保留错误记录供审查，不一律判失败。工具失败也不等于整轮失败，可能是先失败后修复的测试。`execution_complete` **不代表任务验收通过**。

## 停止和恢复

在具体轮次目录创建 `STOP`，或向 runner 发送 SIGINT/SIGTERM。runner 保存原因，先终止自己创建的进程组，宽限后强制结束仍在该组内的进程；不杀其他 pi 会话。正常退出也清理组内残留子进程，派工时不要要求 pi 启动需要跨轮存活的后台服务。

退出码：0 为轮次执行完整；1 为启动、协议或最终状态失败；124 为超时；130 为停止请求。启动前参数错误通常为 2。每个新轮目录不可覆盖。

SIGKILL、宿主崩溃和脱离进程组的子进程无法由本 runner 保证清理；`meta.json` 可能仍为 running。此时查实际进程/作业容器、原始事件、session 与工作区，确认停止后再续跑。锁文件会保留，但 flock 随持有进程退出释放；不要删锁文件，否则可能出现两个不同 inode 的锁。

续跑使用同一 session 的新轮次，prompt 描述中断原因、已完成部分、最新修正和接下来的验收条件。先检查部分写入，不盲目重复命令。超时后的输出只能说明已经观察到的进展，不能作为最终结果。

## 协议来源与维护

2026-10-26 对照本机 1.3.0、Context7 版本文档和以下官方源文件核对：

- [CLI integration](https://github.com/earendil-works/pi/blob/v1.3.0/packages/coding-agent/docs/cli-integration.md)
- [JSON event stream](https://github.com/earendil-works/pi/blob/v1.3.0/packages/coding-agent/docs/json.md)
- [CLI options](https://github.com/earendil-works/pi/blob/v1.3.0/packages/coding-agent/docs/cli.md)

升级 pi 后先跑 `python3 -m unittest discover -s skills/pi-supervision/scripts -p 'test_*.py'`，再在空目录做两轮无工具 smoke，验证模型选择、会话记忆、最终状态和留档。模拟测试不能替代当前发行版的真实协议验证。
