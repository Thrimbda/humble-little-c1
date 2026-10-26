---
name: pi-supervision
description: 当用户要求调度本机 pi-coding-agent（Pi）执行任务、由当前 agent supervise，或需要逐轮保存 prompt/输出、回传进展、检查结果和中断续跑时使用。适用于用户已配置的 provider/model，包括 deepseek-flash；不用于普通代码问答或无关的多 agent 编排。
---

# Pi Supervision

把 pi 当作受监督的执行者：当前 agent 负责理解目标、派工、纠偏和验收，pi 负责有边界的实现。默认保持一个 RPC 进程，通过 stdin 发指令、stdout 收事件；执行完成不能替代任务验收。

## 1. 先确定目标和现场

从会话提取最终目的、用户修正、验收证据和授权范围。不要把某个手段当成目的：例如“统一模型”可能是为了共享信息，删除旧名称并不能证明信息已经共享。把这些写入任务目录的 `objective.md`，无需重复询问已确认的事项。

检查目标仓库的规则、工作区状态、宿主系统、现有工具链，以及 `pi --version`、`pi --help`。按需读取 [运行与协议](references/runtime.md)。

- 优先使用项目已有的开发环境。**只有识别到 NixOS 或项目使用 Nix 时，才选择对应的 Nix 做法**；macOS、其他 Linux、容器和 Windows 按各自环境处理。
- 显式选择用户指定的 provider/model。未指定时查看已有配置，说明所选模型；不能静默切换。不要输出认证文件或密钥。
- 在合适的 checkout/worktree 内执行，并记录实际 cwd、提交和未提交状态。遵循仓库隔离规则，不重置用户改动。
- 先确定工具权限和资源预算。附带 runner 是 POSIX/Python 3 工具，控制普通进程组和超时，不是安全沙箱，也不设置内存上限。Windows 需经验证的 WSL 或原生作业管理适配；重负载按现场选择 cgroup、容器等。

## 2. 每轮给一个可验收的任务

任务目录使用私有权限，放在仓库外；同一任务固定一个绝对 session 路径，每轮单独目录，旧轮次不覆盖。用 [轮次模板](references/round-template.md) 写 prompt，包含：

1. 最终目标、当前轮目标、用户最新修正。
2. 已核实的宿主、cwd、输入、允许修改范围和限制。
3. 本轮需要产生的行为、验证方式和输出要求。
4. 前一轮监督审查发现的问题及证据（若有）。

一轮尽量解决一个可检查的增量。先让 pi 理解现状和调用链，再实现、验证、修正；不要机械规定轮数，也不要把所有检查留到最后。与用户同步派发的 prompt 内容，长文本给出完整文件链接并贴出关键要求。

## 3. 执行、持续读取并回传

先阅读 [运行与协议](references/runtime.md)，运行 `scripts/run_session.py --help`。以显式 provider/model 和固定 session 启动一次 runner；它启动 `pi --mode rpc`，保持双向 stdio。收到 `ready` 后，通过 runner 的 stdin 发 JSONL `prompt`，每轮用新的 `round` 和绝对 `prompt_file`。运行中可发 `steer` 或 `follow_up`；它们归当前轮留档。收到 `round_finished`、独立审查后，再向同一进程派发下一轮。

先做短 smoke 核对当前版本的协议。不要用含糊的 `--continue` 选“最近会话”；RPC 不接收 `@file`，runner 会读取 prompt 文件并通过 stdin 发送内容。保留 `run_round.py` 仅作明确选择的单轮 JSON/print 备用路径。

脚本逐轮保存 `prompt.md`、`inputs.jsonl`、`events.jsonl`、`output.md`、`live.txt`、`stderr.log`、`meta.json`，会话另存完整控制命令与跨轮事件。运行中追加或纠偏的文字也在 inputs 中，不只保存最初的 prompt。原始记录留在本机，分享前遮盖凭据，不自动提交到仓库。

**存盘和向用户回传是两件事。** runner 持续等待并读取管道事件，不轮询日志文件。宿主只能分次获取命令输出时，监督者在外层短等待读取新增输出；这不改变 runner 与 pi 的双向 stdio。每轮回传 prompt、pi 文字（较长时附原文链接）、监督结论和下一步，运行中默认不超过 60 秒没有进度消息。保持 stdin 打开；EOF 会取消活跃轮并关闭会话。

## 4. 监督者独立验收

先检查 `round_finished.status` 和轮次元数据：RPC `response.success` 仅表示命令处理成功；`handled` 不代表模型执行过任务。执行完整要求相关响应已收齐、最终 assistant 为 `stop`、收到未 aborted 的 `agent_settled` 且流无损坏。持久进程在轮间继续存活，不等待每轮进程退出；会话关闭时再核对退出状态。`agent_end` 后可能重试；保留已恢复错误而不误判终态。

再检查任务是否完成：自己读 diff、追踪真实入口和数据流，并运行与改动相称的检查。测试通过不能代替审查测试是否覆盖用户要求。关注真实调用方是否传入新信息、旧分支是否仍截断数据、来源和时间语义是否一致；单独 helper 测试不证明集成有效。

写 `review.md`，区分 **pi 的声明 / 监督者观察 / 已运行验证 / 未验证边界**，给出接受、返工或阻塞结论。发现问题时在新轮次附上复现证据、预期行为和新的验收标准，沿用原 session。不要把 pi 自报“完成”直接转成用户结论。

## 5. 中断、续跑与交付

用户修正影响当前实现时，通过 `steer` 排入纠偏；若必须立即停下，向 runner 发 `abort`。runner 先等待 `clear_queue` 成功，再发送 `abort`，避免旧 follow-up 在中断后继续。确认取消完成后可在同一进程开新轮。`shutdown`、stdin EOF 或 SIGINT/SIGTERM 会取消活跃轮并关闭会话；RPC 取消失效时仅清理所拥有的进程组。不使用全局 `pkill pi`。

中断后先核对 pi 已 idle 或退出、session 和部分变更，再创建新轮续跑，不盲目重放写操作。会话异常退出时，以同一精确 session 重启 runner；旧轮不可覆盖。锁覆盖持久会话全生命周期；若仍被持有，调查持有者，不删除锁绕过保护。

只有最终目标和验收证据都满足，才交付代码、验证结果、轮次记录入口及剩余限制。版本冻结、提交、PR 或发布按用户要求及仓库规则处理；记录精确提交、版本和验证范围，不能把“存在一个版本号”视为已冻结。此 skill 本身不授权合并、部署或对外发消息。
