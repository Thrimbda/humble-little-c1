# 协议参考

以下字段按 Codex CLI **0.160.1** 的生成 schema 校验。`MODEL_FROM_CATALOG`、`THREAD_ID`、`TURN_ID` 和 `ITEM_ID` 代表运行时取得的值；路径换成目标服务器上的绝对路径。示例不是固定模型目录。

## 消息 envelope 与传输

省略 `jsonrpc` 字段。根据字段组合分派消息，`id` 可为字符串或整数，要检查字段是否存在，不能用真假值判断 `id`：

| 字段 | 含义 | 客户端动作 |
| --- | --- | --- |
| `id` + `result` | 成功响应 | 完成该 ID 的等待请求 |
| `id` + `error` | 失败响应 | 记录 `code`、`message`、可选 `data` |
| `id` + `method` | 服务器请求 | 处理后回复相同 ID |
| `method`、没有 `id` | 通知 | 更新状态，不回复 |

stdio：将紧凑 JSON 后加换行，flush，持续解析 stdout。stderr 是诊断输出，不与协议混合。

Unix WebSocket：先在 Unix socket 上完成 HTTP Upgrade，再收发 WebSocket 文本消息。交给支持 Unix socket 的 WebSocket 库处理握手、mask、分片与 ping/pong，不能把 `recv()` 的任意字节块当成完整 JSON。

### 直接连接已有 Unix socket 的只读示例

下面程序需要 Python 的 `websockets` 包，使用已核对的 `websockets.asyncio.client.unix_connect` 接口。将它保存为脚本，以实际 socket 路径作为第一个参数运行。它只初始化连接并读取模型目录，不创建会话。

```python
import asyncio
import json
import sys
from websockets.asyncio.client import unix_connect

async def main(path):
    async with unix_connect(path, uri="ws://localhost/", open_timeout=10,
                            max_size=16 * 1024 * 1024) as ws:
        # 仅用于这个串行、只读探测；完整客户端使用下文的持续 dispatcher。
        async def rpc(request_id, method, params):
            await ws.send(json.dumps({"id": request_id, "method": method,
                                      "params": params}))
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 30))
                if "method" in msg:
                    if "id" in msg:
                        await ws.send(json.dumps({"id": msg["id"], "error": {
                            "code": -32601, "message": "Unsupported by read-only probe"}}))
                    continue
                if msg.get("id") == request_id:
                    if "error" in msg:
                        raise RuntimeError(msg["error"])
                    return msg["result"]

        await rpc(1, "initialize", {"clientInfo": {
            "name": "codex_usage_probe", "version": "0.1.0"},
            "capabilities": {"experimentalApi": False}})
        await ws.send(json.dumps({"method": "initialized"}))
        cursor = None
        request_id = 2
        while True:
            page = await rpc(request_id, "model/list", {"cursor": cursor, "limit": 100})
            for model in page["data"]:
                print(json.dumps({key: model[key] for key in (
                    "model", "defaultReasoningEffort", "supportedReasoningEfforts")}))
            cursor = page.get("nextCursor")
            if cursor is None:
                break
            request_id += 1

asyncio.run(main(sys.argv[1]))
```

在该版本中，`codex app-server proxy --sock ...` 只转发原始字节；如果经过 proxy，发送和接收的仍是 WebSocket 握手与帧。若要 JSONL，使用明确提供 stdio transport 的 app-server；这会启动独立服务。

## 最小会话链路

下文每个 JSON 对象是一条消息。WebSocket 一条文本消息传一个对象；stdio 将每个对象压成一行后发送。先等待初始化成功：

```json
{"id":1,"method":"initialize","params":{"clientInfo":{"name":"codex_usage_client","title":"Codex Usage","version":"0.1.0"},"capabilities":{"experimentalApi":false}}}
```

```json
{"method":"initialized"}
```

查询模型，分页读取 `result.data` 与 `result.nextCursor`：

```json
{"id":2,"method":"model/list","params":{"limit":100}}
```

从目录的 `model` 字段取得模型名称，并确认支持 `high` 后，以默认 Auto Review 创建持久会话：

```json
{"id":3,"method":"thread/start","params":{"cwd":"/absolute/project","ephemeral":false,"model":"MODEL_FROM_CATALOG","config":{"model_reasoning_effort":"high"},"approvalPolicy":"on-request","approvalsReviewer":"auto_review","sandbox":"workspace-write"}}
```

读取 `result.thread.id`，并检查 `result.model`、`result.reasoningEffort`、`cwd`、`approvalPolicy`、`approvalsReviewer` 与 `sandbox` 有效值。确认 reviewer 为 `auto_review`，再开始用户要求的任务：

```json
{"id":4,"method":"turn/start","params":{"threadId":"THREAD_ID","input":[{"type":"text","text":"第一条任务","text_elements":[]}],"model":"MODEL_FROM_CATALOG","effort":"high","approvalPolicy":"on-request","approvalsReviewer":"auto_review","sandboxPolicy":{"type":"workspaceWrite"}}}
```

保存 `result.turn.id`。响应可能是 `inProgress`，持续处理事件直至目标 turn 完成。0.160.1 文本输入的 `text_elements` 在 schema 中可省略，显式空数组也合法。

第二条消息等当前 turn 完成后发送；省略 model/effort 则沿用当前 thread 设置：

```json
{"id":5,"method":"turn/start","params":{"threadId":"THREAD_ID","input":[{"type":"text","text":"第二条任务","text_elements":[]}]}}
```

重连时重新初始化，按当前选定权限模式先 resume 再发送下一条任务。默认 Auto Review 的恢复请求：

```json
{"id":6,"method":"thread/resume","params":{"threadId":"THREAD_ID","approvalPolicy":"on-request","approvalsReviewer":"auto_review","sandbox":"workspace-write"}}
```

`thread/resume` 不会自动启动新 turn。不要用 `thread/fork` 代替继续原会话，它会生成新 ID。

## 权限模式示例

上面的新建、执行与恢复示例显式设置 Auto Review。`on-request` 决定哪些操作需要审批，`auto_review` 决定由自动 reviewer 处理；工作区内已允许的操作不会每次都触发 review。检查新建/恢复响应的 reviewer，不能以字段被接受就认定自动审批已经生效。

用户指定 Full access 时，新建会话可使用：

```json
{"id":20,"method":"thread/start","params":{"cwd":"/absolute/project","ephemeral":false,"approvalPolicy":"never","sandbox":"danger-full-access"}}
```

在已有 thread 开始 turn 时设置完全权限，`sandboxPolicy` 必须是对象：

```json
{"id":21,"method":"turn/start","params":{"threadId":"THREAD_ID","input":[{"type":"text","text":"用户要求的任务","text_elements":[]}],"approvalPolicy":"never","sandboxPolicy":{"type":"dangerFullAccess"}}}
```

恢复之前选定 Full access 的会话时，在 `thread/resume` 传 `approvalPolicy: "never"`、`sandbox: "danger-full-access"`，不套用默认 Auto Review 的恢复示例。切回 Auto Review 时重新设置 `on-request`、`auto_review` 与相应 sandbox。

`never` 不等于“自动批准”，也不解除 sandbox；完全权限必须同时设置 `danger-full-access` / `dangerFullAccess`。此模式不执行 Auto Review，仍需遵守目标进程和外部服务的有效权限。不要选择人工 Ask 模式，也不要在自动审批不受支持、被拒绝或失败时回退到人工 reviewer 或自行改成完全权限。

## 持续 dispatcher 与完成条件

启动接收循环后再发 RPC，确保通知即使先于响应到达也能被记录。客户端维护两类状态：

```text
pendingRequests[requestId]              请求等待者
items[threadId, turnId, itemId]          输出及 item 状态

收到 response → 完成/拒绝匹配的 pendingRequests
收到 server request → 按 method 与用户授权处理，回复原 id
收到 notification → 更新对应 thread/turn/item 状态
```

注册等待者、保存已观察的完成状态后再等待，避免丢失提前到达的 `turn/completed`。重连时拒绝旧连接未完成的 RPC 等待者；“没有响应”不等于服务器没有执行。

典型文本 delta：

```json
{"method":"item/agentMessage/delta","params":{"threadId":"THREAD_ID","turnId":"TURN_ID","itemId":"ITEM_ID","delta":"部分文本"}}
```

`item/completed.params.item.type == "agentMessage"` 时，将该 item 的文本替换为 `item.text`。保留多个 item 的顺序；有 `phase` 时区分 commentary 与 final_answer，不把所有消息揉成一份最终答复。是否存在这些字段以当前 schema 为准。

`turn/completed.params` 包含 `threadId` 与完整 `turn`；只接受匹配 turn ID 的完成事件，检查 `turn.status`。命令日志、思考流或任意一个 `item/completed` 都不是整个任务完成的证据。

服务器请求的回复 envelope，例如用户已经拒绝某个命令审批时：

```json
{"id":"SERVER_REQUEST_ID","result":{"decision":"decline"}}
```

这里的 `id` 换成服务器请求原值，保留原类型。`decision` 必须匹配该 method 的响应类型；命令审批、文件审批、权限申请、用户问题、动态工具调用各有不同 schema。操作结果和用户回答按真实授权返回。

执行中追加与中断：

```json
{"id":7,"method":"turn/steer","params":{"threadId":"THREAD_ID","expectedTurnId":"TURN_ID","input":[{"type":"text","text":"对当前任务的追加指示","text_elements":[]}]}}
```

```json
{"id":8,"method":"turn/interrupt","params":{"threadId":"THREAD_ID","turnId":"TURN_ID"}}
```

中断响应 `{}` 只是接受请求，仍应等目标 turn 的终止状态；`interrupted` 与成功完成分开报告。

## 按项目列出全部 session

先使用前文的 `initialize` / `initialized` 完成连接初始化。以下操作只读取会话列表，不需要 `model/list`、`thread/start`、`thread/resume` 或 `turn/start`。

### 查询范围与首个请求

在目标服务器对应版本的生成 schema 中查看 `ThreadListParams`、`ThreadListResponse` 和 `ThreadSourceKind`。0.160.1 的 `ThreadSourceKind` 完整枚举为下方十项；其他版本重新读取枚举，不把这个示例当成永久固定列表。

`cwd` 精确匹配会话记录的工作路径，可以是一个字符串或多个路径的数组。示例中的第二个路径只代表已确认属于同一项目的 worktree；不会自动包含其他子目录或 worktree。路径使用目标机器上的绝对路径；若记录使用另一条路径或符号链接形式，先核对实际 cwd，不凭路径前缀判断归属。

首个请求覆盖这两个 cwd 的全部来源、未归档会话：

```json
{
  "id": 30,
  "method": "thread/list",
  "params": {
    "cwd": ["/absolute/project", "/absolute/project/.worktrees/example"],
    "sourceKinds": ["cli", "vscode", "exec", "appServer", "subAgent", "subAgentReview", "subAgentCompact", "subAgentThreadSpawn", "subAgentOther", "unknown"],
    "archived": false,
    "limit": 100,
    "sortKey": "updated_at",
    "sortDirection": "desc"
  }
}
```

不要省略 `sourceKinds` 或传空数组来表示“所有来源”：这会使用默认交互来源。`modelProviders` 省略、`null` 或 `[]` 时包含所有 provider；完整查询省略它，也不添加 `searchTerm`、`originators`、`sectionId` 等额外过滤条件。

### 响应、分页与归档

从 `result.data[]` 读取 thread，保留真实 `id`、`name`（可为空）、`preview`、`cwd`、`source`、`status` 与 `updatedAt`。`updatedAt` 为 Unix 秒时间戳；`source` 可能是字符串或 sub-agent 等结构，按返回值保留。列表中的 `turns` 为空，不能从列表读取完整历史。

后续页复制同一组查询条件，加入上一页的 `result.nextCursor`，并使用新的 RPC ID。cursor 是不透明字符串，不解析或自行生成；即使某页 `data` 为空，只要还有 `nextCursor` 就继续。直到 cursor 为 `null` 或不存在，才完成该查询。

再以相同 cwd、来源及排序条件、`archived: true` 开始新的完整遍历；第一请求不携带未归档查询的 cursor。`archived: true` 只查归档，`false`、省略或 `null` 只查未归档，没有省略此字段就返回两类的语义。归档标记由查询条件附到清单，不假设 thread 自带 `archived` 字段。

### 可复用的分页函数

下面函数接收前文已初始化连接上的串行 `rpc` 函数、明确的项目 cwd 数组与从目标 schema 读取的完整 `source_kinds`。在 `main` 中调用 `await list_project_threads(rpc, project_cwds, source_kinds)`，即可用其返回值展示清单。示例为 0.160.1 的 cwd 数组接口；仅支持字符串的旧版本逐路径调用后按 ID 合并。请求 ID 从 100 开始，调用方应避免与同连接其他请求重复。

```python
async def list_project_threads(rpc, project_cwds, source_kinds):
    if not project_cwds or not source_kinds:
        raise ValueError("Provide project cwd paths and all schema source kinds")
    base = {"cwd": project_cwds, "sourceKinds": source_kinds, "limit": 100,
            "sortKey": "updated_at", "sortDirection": "desc"}
    rows = {}
    request_id = 100
    for archived in (False, True):
        cursor = None
        while True:
            params = {**base, "archived": archived}
            if cursor is not None:
                params["cursor"] = cursor
            page = await rpc(request_id, "thread/list", params)
            request_id += 1
            for thread in page["data"]:
                rows[thread["id"]] = {
                    "threadId": thread["id"], "name": thread.get("name"),
                    "preview": thread["preview"], "cwd": thread["cwd"],
                    "source": thread["source"], "status": thread["status"],
                    "updatedAt": thread["updatedAt"], "archived": archived,
                }
            cursor = page.get("nextCursor")
            if cursor is None:
                break
    return sorted(rows.values(), key=lambda row: row["updatedAt"], reverse=True)
```

`rpc` 应像前文那样将错误响应或超时抛出，不将它们转换为成功的空页。某页失败时，此函数不返回一个貌似完整的清单；需要交付部分结果的客户端单独保留已取得页，明确缺口。完整遍历后按 thread ID 去重，并注明服务器/存储、cwd、来源、归档范围与分页完成情况；这是该次查询的覆盖范围，不是另一套存储或查询期间所有变化的一致快照。

`thread/loaded/list` 只查当前服务内存中的 thread ID，不能替代这个持久化清单。临时会话或另一套 `CODEX_HOME` 中的会话也不由上述查询覆盖。用户选定真实 `threadId` 后，按下一节读取历史；用户要求继续时，按[最小会话链路](#最小会话链路)恢复并发送下一条任务。

## 读回历史

只读历史，不恢复执行：

```json
{"id":9,"method":"thread/read","params":{"threadId":"THREAD_ID","includeTurns":true}}
```

传统完整历史读取：检查 `result.thread.turns[].items`，从 `type == "agentMessage"` 的 item 取得 `text`。

分页历史：先获取 thread 元数据；若当前版本支持 `thread/turns/list`，读取所有 turn 页，选择 `itemsView: "full"`：

```json
{"id":10,"method":"thread/turns/list","params":{"threadId":"THREAD_ID","limit":50,"sortDirection":"asc","itemsView":"full"}}
```

检查返回 turn 的 `itemsView`。`summary` 或 `notLoaded` 不代表完整 items；缺少完整 item 时，使用可用的 `thread/items/list`：

```json
{"id":11,"method":"thread/items/list","params":{"threadId":"THREAD_ID","turnId":"TURN_ID","limit":100,"sortDirection":"asc"}}
```

0.160.1 的 turns 响应为 `result.data[]`；items 响应为 `result.data[]` 的 `ThreadItemEntry`，从 entry 的 `item` 字段读取内容。两者分别跟随 `nextCursor`，把返回 cursor 原样传入下一次同样查询。方法不存在、要求实验能力或 store 不支持时，按该服务器支持的历史接口处理并报告缺口，不能用 summary 声称全文已读回。

持久化验收与推理验收分开：检查用户要求的首个任务的完成状态、新连接读回、[完整列表检索](#按项目列出全部-session)；桌面 UI 是否呈现则另行检查。只列举或读历史时不额外启动任务。不要通过修改 rollout 文件或数据库伪造来源和可见性。

## 参考

- [OpenAI App Server 协议](https://learn.chatgpt.com/docs/app-server#protocol)
- [官方会话列表、分页与过滤说明](https://learn.chatgpt.com/docs/app-server#list-threads-with-pagination--filters)
- [Python websockets Unix 客户端](https://websockets.readthedocs.io/en/stable/reference/asyncio/client.html#websockets.asyncio.client.unix_connect)

Schema 和模型目录使用运行时生成/查询结果，不随本 skill 打包固定快照。
