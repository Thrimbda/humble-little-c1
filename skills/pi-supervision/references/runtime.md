# 运行与协议

## 现场选择

先确认 `pi --version`、`pi --help`、项目指令和开发环境。不同发行版可能同名；核对安装包来源及当前版本文档，不能套用另一 fork 的参数。文档检索遵循宿主约定。

| 现场 | 选择 |
| --- | --- |
| 项目有已验证的 dev shell / 容器 | 在其中启动 runner，让 pi 继承工具链 |
| NixOS，缺工具或遇到 ELF loader 问题 | 优先已有 flake/devShell，必要时选合适的 `nix develop` / `nix shell`；不假定 apt、FHS 路径或预编译二进制可用 |
| 其他 Linux / macOS | 使用已有工具链，不为这个 skill 安装 Nix |
| Windows | 流程适用；附带 runner 要求 POSIX，需验证 WSL 或原生适配 |
| 必须限制内存或终止脱离进程组的子进程 | 使用已验证的 cgroup / 容器 / 作业管理器，并记录实际配置 |

systemd 是独立能力，不等同于 NixOS。runner 不设置内存上限，不是安全沙箱。不要为普通调度改动系统配置。

## 启动一次，多轮使用

runner 依赖 POSIX 和 Python 3.9+ 标准库。将下面路径替换为已核实的绝对路径；模型使用用户指定、已配置的值：

```bash
python3 /path/to/pi-supervision/scripts/run_session.py \
  --cwd /path/to/project \
  --run-dir /path/to/private-task-records \
  --provider deepseek --model deepseek-flash \
  --tools read,grep,find,ls \
  --timeout-seconds 600 --idle-timeout-seconds 1800
```

runner 启动 `pi --mode rpc --provider … --model … --session …`，保持 stdin/stdout 管道。默认 session 为 run-dir 下的 `session.jsonl`；可通过绝对 `--session` 指定。整个持久会话持有 flock，防止另一个 runner 同时写 session；外部绕过 runner 的 pi 仍需监督者自行排查。

`--tools none` 禁用工具；默认 `read,bash,edit,write` 用于已获授权的实现。bash 有完整执行能力，提示中的“只读”不能作为安全隔离。runner 禁用 extensions、skills、prompt templates，本机支持时还禁用 MCP。需要扩展能力时先审查并适配，不静默启用。监督者仍需读取项目规则并传达，不能假定 pi 的 trust 设置已经加载了它们。

启动后等待 stdout 的 `ready`。保持 runner 的 stdin 打开，通过它发送 LF 结尾的 JSON 对象；每条命令使用不同 `id`。这是 runner 的控制协议，它会转换为 pi RPC 命令：

```json
{"id":"r1","type":"prompt","round":"01","prompt_file":"/path/to/prompt-01.md"}
```

`prompt_file` 必须为绝对路径，也可用 `message` 直接提供文字，两者选一。RPC 本身不支持命令行 `@file`；runner 读取文件后将内容放入 RPC 的 `message`。文字上限 2 MiB，单个 JSONL 记录和待写缓冲上限 4 MiB，超过限制会明确失败。

收到 `round_finished` 后先做独立审查，再向**同一个 runner**发送下一轮：

```json
{"id":"r2","type":"prompt","round":"02","prompt_file":"/path/to/prompt-02.md"}
```

下一轮不能与当前轮并发。`round` 是新的目录名，已有目录拒绝覆盖；session 与 pi PID 保持不变。最后发送：

```json
{"id":"end","type":"shutdown"}
```

收到 `session_closed` 并核对进程退出 0 后，正常会话才算关闭。会话关闭成功不意味着各轮都成功，仍需查看轮次状态。

### 宿主工具如何连接

直接用子进程 API 时，将 runner 的 stdin/stdout 设为 PIPE；先安装持续读取 stdout 的消费者，再写输入，遵守管道背压。不要把两条 prompt 一次性预排好来绕过监督验收。

在 Codex 的终端工具中，可用 `exec_command` 的 `tty: true` 启动 runner，保留返回的 session_id；用 `write_stdin` 发送上面的短 JSON 行，再分次读取新增输出。PTY 可能回显控制行，回显不是 pi 响应；真实 pi 仍由 runner 以 PIPE 连接。长提示走文件，避免终端行长限制。宿主提供原生持久管道时优先用原生管道。

runner 对 pi stdout 做可读事件等待并连续解码，不扫描日志。0.2 秒等待上限用于处理超时、信号和进程退出。监督者通过宿主工具分次收取输出属于外层等待，不是轮询 pi 的日志或反复查询 `get_state`。

不要用 `echo prompt | runner` 后立即关闭输入来等待任务：**stdin EOF 表示关闭会话**，会取消活跃轮。外层消费者也应保持读取，否则 stdout 背压会阻塞整个链路。

## 运行中纠偏与取消

等初始 prompt 的 RPC 响应确认 `started` 后，当前轮运行中可发送：

```json
{"id":"fix1","type":"steer","message":"更新约束：继续使用项目现有工具链。"}
{"id":"more1","type":"follow_up","prompt_file":"/path/to/additional-check.md"}
```

steer 在当前 assistant 的工具调用结束后、下一次模型调用前交付；follow_up 在当前工作完成后交付。二者都归当前轮，输入和后续输出一起保存；不要用 follow_up 预授权依赖本轮审查的下一阶段。命令响应为 `queued` 只代表接受排队，不代表任务完成。

追加指令与 settled 可能竞争。如果观察到已经 settled 后才确认排队，runner 会清队列、取消并标记 `incomplete`，避免把可能没有执行的追加任务算作完成。检查记录后在新轮重述未完成要求。

必须立即停下时发送：

```json
{"id":"stop1","type":"abort"}
```

runner 等 `clear_queue` 成功后才发送 `abort`；单独 abort 可能继续执行旧队列。取消等待有界，默认宽限 10 秒。收到 `round_finished` 的 `cancelled` 后核对部分改动，再在同一进程开新轮。若 RPC 取消无响应，runner 清理其进程组并以失败退出，留下已收数据。

`shutdown`、stdin EOF 或 SIGINT/SIGTERM 都会先取消活跃轮再关闭会话。正常关闭通过 pi stdin EOF 请求退出；超时才定向终止自己的进程组，不使用全局 `pkill pi`。后台子进程可能跨轮存活，只在会话关闭时清理组内进程；不要把跨任务服务托管给 runner。SIGKILL、宿主崩溃或脱离进程组的子进程需要现场排查。

## 输出、留档与完成判定

runner 的 stdout 始终输出 JSONL：`ready`、`command_sent`、`command_error`、`pi_event`、`pi_stderr`、`round_finished`、`session_closed` 或 `session_error`。`command_sent` 只表示进入发送队列；要看具有对应 id 的 pi `response` 确认已接收。`pi_event.event` 保存完整 pi 事件，`text_delta` 可立即用于回传。完整消息以 `message_end.message` 为准，不能将 delta 与最终文本重复拼接。

| 位置 | 内容 |
| --- | --- |
| `rpc-<id>/controls.jsonl` | 监督者发给 runner 的完整原始控制输入，含无效命令 |
| `rpc-<id>/inputs.jsonl` | 发往 pi 的完整 JSONL 命令；发送失败时可能仅部分写入，结合响应判断 |
| `rpc-<id>/events.jsonl`、`stderr.log` | 跨轮原始 stdout 与独立 stderr |
| `rpc-<id>/meta.json` | 启动参数、版本、session、PID、各轮状态和会话退出状态 |
| `<round>/prompt.md`、`inputs.jsonl` | 初始 prompt，以及当前轮的完整 RPC 输入，包括追加和取消命令 |
| `<round>/events.jsonl`、`output.md`、`live.txt` | 当前轮事件、所有已结束 assistant 文字、流式部分文字 |
| `<round>/stderr.log`、`meta.json` | 当前轮诊断及执行状态、错误、最终消息信息 |
| `<round>/review.md` | 监督者另外写的独立验收结论 |

stderr 是独立管道，按读取时的活跃轮次附存；跨管道没有严格事件顺序，全局 stderr 记录为完整依据。失败时未解码的尾部字节仍保存在原始事件中。文件为私有权限，不输出密钥、不自动提交原始日志；分享前制作必要的脱敏副本。

`execution_complete` 要求相关 RPC 响应收齐、最终 assistant `stopReason=stop`、未 aborted 的 `agent_settled`、协议无错误。`agent_end` 后可重试，不能当最终完成。早期 error 若恢复可以成功，但错误历史保留。工具失败由监督者判断是否已经修复。

`handled` 表示输入被处理但未启动模型运行，不能计为任务完成，也无需等待不存在的 settled。`rejected`、`incomplete`、`cancelled`、`timeout`、`failed` 均不能作为完成证据。正常 RPC 会话持续运行，轮次完成时没有进程退出码；异常退出会标记会话失败。runner 正常关闭返回 0，执行/协议故障返回 1，参数错误通常返回 2；**会话退出 0 不等于每轮通过**。

会话失败后先检查进程、session、部分改动与未执行队列，再用相同 session、新轮目录重启；不自动重放写操作，不删除锁文件绕过保护。锁文件保留，flock 随持有进程退出释放。

## 单轮备用路径

明确需要每轮退出进程时可使用 `scripts/run_round.py --help`，传入 `--cwd`、`--run-dir`、`--round`、`--prompt`、provider/model。它使用 JSON/print、stdin 关闭、固定 session 跨进程继续，不接受运行中追加指令。取消用轮目录 `STOP` 或信号；退出码为 0/1/124/130。它不是 RPC 主路径，不要把两种控制方式混用。

## 协议来源与验证

对照本机 earendil-works/pi-coding-agent **1.3.0** 和官方版本文档：

- [RPC stdio、命令响应与关闭](https://github.com/earendil-works/pi/blob/v1.3.0/packages/coding-agent/docs/rpc.md)
- [prompt、steer、follow_up、clear_queue、abort](https://github.com/earendil-works/pi/blob/v1.3.0/packages/coding-agent/docs/rpc-commands.md)
- [JSON event stream](https://github.com/earendil-works/pi/blob/v1.3.0/packages/coding-agent/docs/json.md)

升级后运行 `python3 -m unittest discover -s skills/pi-supervision/scripts -p 'test_*.py'`，再做实际模型两轮记忆、流式追加、取消及关闭 smoke。不要为了兼容不同版本删掉完成检查。
