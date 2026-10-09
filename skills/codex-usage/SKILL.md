---
name: codex-usage
description: 当需要通过 Codex app-server 的 socket 或 RPC 按项目列出全部 thread/session、读取历史、创建或继续会话、接收输出、选择模型与工具权限，或核对 schema 和列表可见性时使用。
---

# Codex Usage

通过目标 Codex app-server 操作会话。协议中的 **thread** 是持续会话，**turn** 是一次用户输入及其执行过程；保存 `threadId`，后续消息继续使用它。

**协议以目标服务器对应版本生成的 schema 为准。** 先确认连接到哪台机器、哪个 app-server、哪套会话存储，再发送 RPC。详细消息与直连示例见[协议参考](references/protocol.md)。

## Codex App Server 交互

从连接、发现已有会话到执行与读回结果，都在本章选择对应操作。用户要求“列出某个项目的全部 session”时，优先走[按项目列出全部 session](#4-按项目列出全部-session)；列举和读历史无需创建或恢复会话，也无需启动 turn。

| 目的 | 交互入口 | 关键区别 |
| --- | --- | --- |
| 建立连接 | 确认 transport；`initialize` → `initialized` | 每条新连接初始化一次 |
| 查看模型与思考强度 | `model/list` | 选模型时查询，不是列举会话的前置条件 |
| 列出项目的持久会话 | `thread/list` | 明确 cwd、来源、归档范围，并取完所有页 |
| 查看当前加载的会话 | `thread/loaded/list` | 内存列表，不能替代持久化列表 |
| 只读已有历史 | `thread/read`；支持时用 `thread/turns/list`、`thread/items/list` | 不恢复执行，不订阅实时输出 |
| 创建并执行 | `thread/start` → `turn/start` | 保存 thread/turn ID，持续接收事件 |
| 继续已有会话 | `thread/resume` → `turn/start` | 沿用原 thread ID；`thread/fork` 会生成新 ID |
| 给运行中的任务追加指示 | `turn/steer` | 使用当前 `expectedTurnId` |
| 中断运行中的任务 | `turn/interrupt` | 等待目标 turn 的终止状态 |
| 接收与恢复输出 | 持续 dispatcher；断线后读回完整 items | 区分 RPC 响应、服务器请求和通知 |

### 1. 确认版本与连接入口

```bash
command -v codex
codex --version
codex app-server --help
codex app-server proxy --help
codex app-server daemon version
```

支持时可用 `codex doctor --summary` 查看运行模式和服务信息。`daemon version` 连接失败不代表整个 Codex 不可用：当前客户端可能连接另一个 endpoint，或运行在 embedded/ephemeral 模式，没有可供外部连接的 control socket。

默认 control socket 通常是 `${CODEX_HOME:-$HOME/.codex}/app-server-control/app-server-control.sock`，实际路径从目标服务的运行信息核对。远端服务在远端检查；本地同名路径不能证明指向同一服务。若 CLI 与服务器版本不同，使用服务器对应的 binary 生成协议，不用 GitHub `main` 替代。

| 入口 | 传输约定 | 使用条件 |
| --- | --- | --- |
| 已有 Unix control socket | 先确认该版本的 socket framing；0.160.1 是 HTTP Upgrade 后的 WebSocket，每个文本消息一条 RPC | 直接连接目标现有服务 |
| `codex app-server proxy --sock /absolute/control.sock` | 0.160.1 只双向转发原始字节，不转换 WebSocket 与 JSONL | 连接已有 socket；客户端仍需实现该 socket 的 framing |
| `codex app-server --listen stdio://` | 每行一条 JSON，stdin/stdout 保持打开 | 启动独立 app-server，需确认它使用的存储是否符合用户目的 |
| 已有 TCP WebSocket endpoint | 每个文本消息一条 RPC，遵循 endpoint 的认证要求 | 连接用户指定的服务 |

不要把 JSONL 直接写入已确认使用 WebSocket 的 socket 或原始字节 proxy。旧版本可能使用不同 framing，先核验，再选客户端。`proxy` 不负责启动 daemon，也不保证让会话出现在桌面侧栏。需要新服务时，可按当前 CLI 帮助启动；已有服务的 restart/update 不属于连接步骤。

### 2. 生成并枚举协议

Schema 是 CLI 的生成产物，不是假设存在的 socket `schema/list` 接口。

```bash
schema_dir=$(mktemp -d /tmp/codex-protocol.XXXXXX)
codex app-server generate-json-schema --out "$schema_dir"

for envelope in ClientRequest ClientNotification ServerRequest ServerNotification; do
  printf '\n%s\n' "$envelope"
  jq -r '.oneOf[]?.properties.method | .enum[]?' \
    "$schema_dir/$envelope.json" | sort -u
done
```

- `ClientRequest`：可发送的请求；用 `id` 关联响应。
- `ClientNotification`：客户端通知，例如 `initialized`，不等待响应。
- `ServerRequest`：服务器反向发起的请求，需要客户端回复。
- `ServerNotification`：turn/item/delta 等事件。

从 envelope 中定位 method 的 Params 类型，再读对应 Params/Response 文件；常用类型在 `v1/`、`v2/`，嵌套类型也可能位于 `definitions`。需要代码类型时可运行 `codex app-server generate-ts --out /absolute/generated-dir`。

只有需要实验字段或方法时才生成 `--experimental` 版本，并检查服务器是否要求在 `initialize.capabilities` 中设置 `experimentalApi: true`。导出实验 schema 不会替服务器启用实验功能。

### 3. 初始化并选择模型

每条新连接先发送 `initialize`，等待成功响应，再发送 `initialized`。只列举会话或读历史时可直接调用对应接口。需要选择模型或核对思考强度时，调用 `model/list`，按 `nextCursor` 翻页，读取：

- `model`：发送给 thread/turn 的模型名称；不要用 `displayName` 代替。
- `supportedReasoningEfforts[].reasoningEffort`：该模型支持的思考强度。
- `defaultReasoningEffort`：未指定强度时的默认值。

保留用户指定的模型和强度；缺省时使用服务器默认。模型目录不等于账户权限证明；实际 turn 结果才能验证本次推理是否成功。

0.160.1 的配置位置：

| 时机 | 字段 |
| --- | --- |
| 创建 thread 时指定模型 | `thread/start.params.model` |
| 创建 thread 时指定思考强度 | `thread/start.params.config.model_reasoning_effort` |
| 开始 turn 时调整 | `turn/start.params.model`、`effort` |

`thread/start` 没有顶层 `effort`。读取启动响应中的 `model`、`reasoningEffort` 等有效值，确认配置实际生效。该版本 turn 的 `model`/`effort` 覆盖也影响后续 turns；只想临时调整时，下次显式恢复原值。具体行为仍需核对目标版本的字段说明。

### 4. 按项目列出全部 session

**项目会话查询使用 `thread/list`，不能用 `thread/loaded/list` 代替，也不能只取第一页。** 这里的“全部”指目标服务器及其会话存储中，属于已明确项目路径范围的全部持久会话。临时会话和另一台机器、另一套 `CODEX_HOME` 中的会话不由这个列表覆盖。

1. **确认服务器与项目范围。** 核对服务器、用户身份、会话存储与 `CODEX_HOME`。使用目标机器上的绝对项目路径。0.160.1 的 `cwd` 是精确匹配，不递归匹配子目录，也不自动把 worktree 合并为同一项目。若用户要覆盖已确认的子目录或 worktree，收集对应 cwd；该版本支持 `cwd` 路径数组。旧版本若只支持字符串，逐路径查询。不要把项目名、目录前缀或 Git remote 相同直接当作 cwd 相等。
2. **显式覆盖全部来源。** 从目标版本 schema 的 `ThreadSourceKind` 取得全部枚举值，作为 `sourceKinds`。省略或传 `[]` 只查默认交互来源；只写 `cli`、`vscode`、`exec`、`appServer` 也会漏掉 sub-agent 等来源。完整查询时不额外设置 provider、标题、来源客户端或侧栏分组过滤器。
3. **分别遍历未归档和已归档会话。** `archived: false` 查询未归档，`archived: true` 查询已归档；省略或 `null` 不表示两类全查。用户要求“全部”时做两次完整遍历；只要未归档时明确报告该范围。
4. **读完每个查询的全部页。** 累积 `result.data`，将 `result.nextCursor` 原样作为下一页的 `cursor`，直到它为 `null` 或不存在。每次只改 cursor 和请求 ID，保持 cwd、来源、归档及排序条件不变；新的路径或归档查询从无 cursor 开始。即使某页 `data` 为空，有下一页 cursor 时也继续。
5. **形成可选择的清单。** 按 `thread.id` 去重，保留 `threadId`、`name`/`preview`、`cwd`、`source`、`status`、`updatedAt`，并用当前查询的 `archived` 值标记归档状态。说明查询目标、路径、来源、归档范围和分页是否完成。`status: notLoaded` 只表示未加载，不代表任务已成功完成。列表是会话元数据，不能当作完整历史。

完整请求、响应字段与分页函数见[项目会话列表示例](references/protocol.md#按项目列出全部-session)。有页失败时报告已取得的清单和缺口，不能声称“全部”；列表为空时先核对服务器、存储和过滤条件。选择某个 `threadId` 后，只读用 `thread/read`，继续任务才用 `thread/resume` 与 `turn/start`。

### 5. 权限模式

**默认使用 Auto Review。** 新建或恢复会话时，显式按选定模式配置权限；不要依赖服务器默认 reviewer。用户指定 Full access 时使用完全权限模式。

| 模式 | `approvalPolicy` | `approvalsReviewer` | `sandbox` |
| --- | --- | --- | --- |
| Auto Review（默认） | `on-request` | `auto_review` | `workspace-write` |
| Full access（完全权限） | `never` | 可省略；不执行审批 review | `danger-full-access` |

- **Auto Review**：工作区边界内的常规工具调用直接执行；需要审批的操作交给 app-server 的自动 reviewer。`on-request` 配合 `auto_review` 是自动审批，不是逐次询问用户。不要用 `never` 来配置 Auto Review，它会关闭审批询问，而不会自动批准需要审批的请求。
- **Full access**：取消 Codex 的文件系统和网络沙箱限制，并且不询问审批。它仍受进程所属用户、管理员策略及外部服务授权限制；不把服务器请求一律回复为批准。

**不选择或自动回退到人工 Ask for approval 模式**，即把交互式审批交给 `approvalsReviewer: "user"`。采用 Auto Review 时，若目标版本不支持、管理员不允许，或返回的有效 reviewer 为 `user`，报告配置限制，不继续发送任务，也不自行改成 Full access 绕过。Full access 使用 `never`，不触发交互式审批，不能仅凭保留的 reviewer 值认定它是人工 Ask 模式。

Auto Review 拒绝、失败或超时时，按真实状态报告，不通过改 reviewer 或无条件批准来绕过。这个规则针对工具审批模式；正常的任务信息补充与工具业务输入仍按实际需要处理。

`thread/start` / `thread/resume` 使用上表的 `sandbox` 字符串。`turn/start` 使用 `sandboxPolicy` 对象：Auto Review 为 `{"type":"workspaceWrite"}`，Full access 为 `{"type":"dangerFullAccess"}`，审批字段名保持不变。覆盖会影响后续 turns；续发与重连保持用户当前选定的模式，切回 Auto Review 时重新显式设置其审批与 reviewer 字段。

检查启动或恢复响应中的有效 `approvalPolicy`、`approvalsReviewer` 与 `sandbox`。Auto Review 应返回 `on-request`、`auto_review` 和 `sandbox.type == "workspaceWrite"`。若用户另行要求只读等 sandbox 边界，保留该边界并继续使用自动 reviewer。具体消息见[权限示例](references/protocol.md#权限模式示例)。

### 6. 创建、执行与继续

1. `thread/start`：传目标机器上的绝对 `cwd`，需持久会话时设 `ephemeral: false`，保存 `result.thread.id`。权限默认显式配置 Auto Review，用户选定其他允许模式时按上节设置。
2. `turn/start`：传 `threadId` 与 `input`。文本输入可写 `{"type":"text","text":"任务内容","text_elements":[]}`；必填项以生成 schema 为准。
3. 同时保存返回的 `turn.id` 并持续接收事件。启动响应只是接受/启动结果，不是最终输出。
4. 当前 turn 完成后，再以相同 `threadId` 发下一次 `turn/start`。
5. 重连后重新初始化。需要继续执行时先 `thread/resume`，然后 `turn/start`；只查看历史时用 `thread/read`，它不会订阅实时输出。

执行中的追加指示使用 `turn/steer`，携带 `expectedTurnId`；中断使用 `turn/interrupt` 的 `threadId` 与 `turnId`。这些操作的语义不同，不用重复 `turn/start` 替代当前 turn 的追加输入。

### 7. 接收输出与读回历史

接收循环同时分派 RPC 响应、服务器请求与通知，不能每发送一次请求就“读一条后退出”。

- `item/agentMessage/delta`：按 `(threadId, turnId, itemId)` 累积文本。
- `item/completed`：用完整 `agentMessage.text` 校正该 item；不要再次拼接到已累积的 delta 后。
- `turn/completed`：匹配目标 thread/turn，并检查 `turn.status`。`completed` 才表示执行成功；`failed`、`interrupted` 单独报告，必要时读取 `turn.error`。
- command、reasoning、progress 等事件与 agentMessage 分开处理，不能当成最终答复。

收到有 `id` 和 `method` 的服务器请求时，按对应 `ServerRequest` 与响应 schema 处理，再回复同一个 `id`。审批、用户输入和动态工具调用不能统一回 `{}`，也不能无条件批准；不支持的请求要明确返回错误。接收循环必须继续运行，否则执行可能一直等待。

读回完整历史时，先看目标版本的历史接口。旧模式可用 `thread/read` 加 `includeTurns: true`；分页模式优先用 `thread/turns/list` 与 `thread/items/list`，跟随各自的 `nextCursor`。不要把 summary items 当成全文。重连后以持久化的完整 item 恢复输出；实时 delta 不保证重放。具体路径见[历史读回示例](references/protocol.md#读回历史)。

连接断开或超时不证明 turn 已停止。重新连接并检查 thread/turn 状态后再决定下一步；不要盲目重发 `thread/start` 或 `turn/start`，以免创建重复工作。

### 8. 验证持久化与列表可见性

需要会话可见时，用实际 `threadId` 验收：

1. 确认创建端与查看端使用同一个服务器/存储、用户身份和 `CODEX_HOME`。另一套远端存储不会因修改查询过滤器而出现本地 thread。
2. 持久会话使用 `ephemeral: false`；完成用户真正要求的首个 turn 后再核对存储。不要只凭零 turn 的启动响应认定已经落盘，也不要为了凑持久化而额外发送无意义任务。
3. 按本章的项目列表流程检索实际 ID，核对 cwd、来源、归档范围及全部分页；不要把已知 ID 的单次读回当成列表可见性证明。
4. 检查返回的实际 `thread.source`，不要断言 app-server 创建的来源固定为 `vscode`。`threadSource` 是 analytics 分类，不是改写 `sourceKinds` 的开关。
5. 需要跨连接保存时，在新连接中用该 ID 读回，并核对列表。RPC 列表验收与桌面 UI 展示分别确认；没有检查 UI 就只报告协议侧结果。

执行任务的交付说明连接目标与版本、有效 model/effort、thread/turn ID、最终状态，以及哪些持久化或 UI 条件尚未验证。仅列举会话时交付清单及查询覆盖范围，不要求额外执行 turn。

## 文档入口

- [OpenAI 官方 App Server 文档](https://learn.chatgpt.com/docs/app-server)：生命周期与协议说明。
- [官方自动审批与权限模式说明](https://learn.chatgpt.com/docs/agent-approvals-security#automatic-approval-reviews)：Auto Review 与 Full access 的区别。
- [官方 App Server 源码说明](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md)：进一步核对实现；注意 `main` 与安装版本可能不同。

连接、权限字段与 Unix/proxy 差异核验于 **2026-10-07**，项目列表字段与示例复核于 **2026-10-09**，均为 **Codex CLI 0.160.1**。使用时重新核对目标版本，避免把这个快照当成所有版本的固定协议。
