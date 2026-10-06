---
name: codex-usage
description: 当需要直接对接 Codex app-server 的 socket 或 RPC 协议，查询本机 schema、创建或继续 thread/session、选择模型与思考强度、接收输出，或排查 session 列表可见性时使用。
---

# Codex Usage

通过目标 Codex app-server 操作会话。协议中的 **thread** 是持续会话，**turn** 是一次用户输入及其执行过程；保存 `threadId`，后续消息继续使用它。

**协议以目标服务器对应版本生成的 schema 为准。** 先确认连接到哪台机器、哪个 app-server、哪套会话存储，再发送 RPC。详细消息与直连示例见[协议参考](references/protocol.md)。

## 1. 确认版本与连接入口

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

## 2. 生成并枚举协议

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

## 3. 初始化并选择模型

每条新连接先发送 `initialize`，等待成功响应，再发送 `initialized`。之后调用 `model/list`，按 `nextCursor` 翻页，读取：

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

## 4. 创建、执行与继续

1. `thread/start`：传目标机器上的绝对 `cwd`，需持久会话时设 `ephemeral: false`，保存 `result.thread.id`。审批和 sandbox 使用当前任务要求或有效默认值。
2. `turn/start`：传 `threadId` 与 `input`。文本输入可写 `{"type":"text","text":"任务内容","text_elements":[]}`；必填项以生成 schema 为准。
3. 同时保存返回的 `turn.id` 并持续接收事件。启动响应只是接受/启动结果，不是最终输出。
4. 当前 turn 完成后，再以相同 `threadId` 发下一次 `turn/start`。
5. 重连后重新初始化。需要继续执行时先 `thread/resume`，然后 `turn/start`；只查看历史时用 `thread/read`，它不会订阅实时输出。

执行中的追加指示使用 `turn/steer`，携带 `expectedTurnId`；中断使用 `turn/interrupt` 的 `threadId` 与 `turnId`。这些操作的语义不同，不用重复 `turn/start` 替代当前 turn 的追加输入。

## 5. 接收输出与读回历史

接收循环同时分派 RPC 响应、服务器请求与通知，不能每发送一次请求就“读一条后退出”。

- `item/agentMessage/delta`：按 `(threadId, turnId, itemId)` 累积文本。
- `item/completed`：用完整 `agentMessage.text` 校正该 item；不要再次拼接到已累积的 delta 后。
- `turn/completed`：匹配目标 thread/turn，并检查 `turn.status`。`completed` 才表示执行成功；`failed`、`interrupted` 单独报告，必要时读取 `turn.error`。
- command、reasoning、progress 等事件与 agentMessage 分开处理，不能当成最终答复。

收到有 `id` 和 `method` 的服务器请求时，按对应 `ServerRequest` 与响应 schema 处理，再回复同一个 `id`。审批、用户输入和动态工具调用不能统一回 `{}`，也不能无条件批准；不支持的请求要明确返回错误。接收循环必须继续运行，否则执行可能一直等待。

读回完整历史时，先看目标版本的历史接口。旧模式可用 `thread/read` 加 `includeTurns: true`；分页模式优先用 `thread/turns/list` 与 `thread/items/list`，跟随各自的 `nextCursor`。不要把 summary items 当成全文。重连后以持久化的完整 item 恢复输出；实时 delta 不保证重放。具体路径见[历史读回示例](references/protocol.md#历史与列表)。

连接断开或超时不证明 turn 已停止。重新连接并检查 thread/turn 状态后再决定下一步；不要盲目重发 `thread/start` 或 `turn/start`，以免创建重复工作。

## 6. 验证 session 列表可见性

需要会话可见时，用实际 `threadId` 验收：

1. 确认创建端与查看端使用同一个服务器/存储、用户身份和 `CODEX_HOME`。另一套远端存储不会因修改查询过滤器而出现本地 thread。
2. 持久会话使用 `ephemeral: false`；完成用户真正要求的首个 turn 后再核对存储。不要只凭零 turn 的启动响应认定已经落盘，也不要为了凑持久化而额外发送无意义任务。
3. `thread/list` 显式包含所需 `sourceKinds`。0.160.1 中省略或 `[]` 只查交互来源；寻找 CLI/exec/app-server 会话时可设 `["cli","vscode","exec","appServer"]`。跟随 `nextCursor`，同时检查 `archived`、`cwd`、provider 等过滤条件。
4. 检查返回的实际 `thread.source`，不要断言 app-server 创建的来源固定为 `vscode`。`threadSource` 是 analytics 分类，不是改写 `sourceKinds` 的开关。
5. 需要跨连接保存时，在新连接中用该 ID 读回，并核对列表。RPC 列表验收与桌面 UI 展示分别确认；没有检查 UI 就只报告协议侧结果。

交付时说明连接目标与版本、有效 model/effort、thread/turn ID、最终状态，以及哪些持久化或 UI 条件尚未验证。

## 文档入口

- [OpenAI 官方 App Server 文档](https://learn.chatgpt.com/docs/app-server)：生命周期与协议说明。
- [官方 App Server 源码说明](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md)：进一步核对实现；注意 `main` 与安装版本可能不同。

本 skill 的具体字段与 Unix/proxy 差异核验于 **2026-10-07，Codex CLI 0.160.1**。使用时重新核对目标版本，避免把这个快照当成所有版本的固定协议。
