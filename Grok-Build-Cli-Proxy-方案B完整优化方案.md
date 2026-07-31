# Grok Build CLI Proxy：方案 B 完整优化设计

## 1. 文档信息

- 项目：`NickyLam/Grok-Build-Cli-Proxy`
- 目标版本：v0.2 ～ v0.6
- 核心方案：**ACP Runtime + OpenAI Responses API + MCP 接口**
- 当前基础：FastAPI、OpenAI Chat Completions 兼容接口、Grok CLI Headless 调用、SSE、会话恢复、WorkBuddy 配置、Bearer Token、并发限制
- 文档目标：将当前“CLI 转 HTTP”代理升级为一个可被应用、IDE 和其他 Agent 使用的本地 Agent API Gateway

---

## 2. 背景与问题定义

当前项目通过以下方式调用 Grok Build：

```text
Client
  └─ POST /v1/chat/completions
       └─ grok-proxy
            └─ spawn: grok -p ...
```

当前实现已经解决：

- OpenAI Chat Completions 基础兼容；
- JSON 和 SSE 输出；
- 指定工作目录；
- Grok Session 恢复；
- 模型自动探测；
- 超时和进程终止；
- Bearer Token；
- 并发数量限制；
- WorkBuddy 自定义模型配置。

但现有架构仍然存在本质限制：

1. `grok -p` 是一次性 Headless 进程，无法自然承载持续的权限询问。
2. 工具调用、计划、工具结果等事件没有完整暴露给调用方。
3. 客户端无法审批 Grok 的文件修改、Shell、网络和 MCP 调用。
4. `Chat Completions` 不适合表达长时间 Agent 任务、后台执行、取消和恢复。
5. 工作区、任务、权限和事件状态主要存在内存中，服务重启后丢失。
6. 当前 Bearer Token 同时代表调用权和最高执行权，不适合多 Agent 或远程使用。
7. Codex、Qoder、CodeBuddy 等 Agent 需要的是 MCP Tool 或 Agent Runtime，而不是只把 Grok 注册成一个聊天模型。
8. 当前默认 `--always-approve`，无法形成真正的人机协同审批闭环。

因此，项目应从：

> OpenAI-compatible CLI Proxy

升级为：

> Stateful Grok Build Agent Gateway with OpenAI-compatible APIs, ACP runtime, tool visibility, human-in-the-loop permissions, workspace isolation and MCP access.

---

## 3. 设计目标

### 3.1 核心目标

1. 保留现有 `/v1/chat/completions` 兼容能力。
2. 新增 `/v1/responses`，表达真实的 Agent 任务生命周期。
3. 内部通过 ACP 连接 Grok Build，保留工具、权限、计划、会话和取消能力。
4. 支持权限询问、审批、拒绝和反馈。
5. 支持长时间任务、后台运行、状态查询、取消和事件重连。
6. 支持工具执行过程可视化，而不只返回最终文本。
7. 支持工作区锁、Git Worktree 隔离和只读运行。
8. 支持 Scoped API Key，分离任务发起权和审批权。
9. 提供 MCP Server，让 Codex、Qoder、CodeBuddy 等 Agent 将 Grok Build 作为外部 Agent 调用。
10. 保持单机优先，同时为后续多用户和远程部署保留边界。

### 3.2 非目标

v0.2～v0.5 阶段不优先实现：

- 公网 SaaS；
- 多租户计费系统；
- 完整云端容器调度；
- 分布式任务队列；
- 将 Grok 的每一个内部事件完全映射为 OpenAI 私有协议；
- 外部客户端接管全部工具执行；
- 直接兼容所有第三方 Agent 协议。

---

## 4. 方案选择

### 4.1 方案 A：继续增强 `grok -p`

优点：

- 改动小；
- 可快速补充工具事件；
- 保留当前代码路径。

缺点：

- 权限询问和恢复困难；
- 每次请求启动新进程；
- 不适合长连接会话；
- 无法自然处理客户端断线后的审批；
- 需要重复实现 ACP 已经提供的能力。

适合作为过渡后端，不作为长期主后端。

### 4.2 方案 B：ACP Runtime + Responses API

内部：

```text
grok agent stdio
```

或：

```text
grok agent serve
```

外部：

- `/v1/chat/completions`
- `/v1/responses`
- `/v1/responses/{id}`
- `/v1/responses/{id}/events`
- `/v1/responses/{id}/cancel`
- `/v1/permissions/{id}/decision`
- MCP Server

优点：

- 原生获得会话、工具、权限和取消能力；
- 适合持续运行；
- 能建立真实的人机审批闭环；
- 可同时服务 HTTP 客户端和 Agent 客户端；
- 更接近实际模型 API 和 Agent API。

缺点：

- ACP Client 实现复杂度较高；
- 需要状态机和持久化；
- 需要区分标准字段与 Grok 扩展字段。

### 4.3 方案 C：只提供 ACP Gateway

优点：

- 最接近 Grok 原生能力；
- 协议转换最少。

缺点：

- WorkBuddy、OpenAI SDK 和普通应用难以接入；
- 不满足已有 HTTP API 用户；
- 生态覆盖不足。

### 4.4 推荐结论

采用方案 B，并保留 HeadlessBackend 作为兼容和回退路径：

```text
HTTP / MCP
    │
    ▼
Response Orchestrator
    │
    ├─ ACP Backend      主路径
    └─ Headless Backend 兼容与回退
```

---

## 5. 总体架构

```text
┌────────────────────────────────────────────────────────┐
│                      API Gateway                       │
│                                                        │
│  /v1/chat/completions                                  │
│  /v1/responses                                         │
│  /v1/responses/{id}                                    │
│  /v1/responses/{id}/events                             │
│  /v1/responses/{id}/cancel                             │
│  /v1/permissions/{id}/decision                         │
│  /v1/models                                            │
│  /health                                               │
│  MCP stdio / Streamable HTTP                           │
└─────────────────────────┬──────────────────────────────┘
                          │
┌─────────────────────────▼──────────────────────────────┐
│                 Response Orchestrator                  │
│                                                        │
│  - Response 状态机                                     │
│  - Session 绑定                                        │
│  - Background Task                                     │
│  - Event Journal                                       │
│  - Cancel / Timeout                                    │
│  - Permission Wait / Resume                            │
└──────────────┬──────────────────┬──────────────────────┘
               │                  │
┌──────────────▼───────┐ ┌────────▼───────────────┐
│ Permission Broker    │ │ Workspace Manager      │
│                      │ │                        │
│ - Policy Engine      │ │ - cwd 校验             │
│ - Approval Requests  │ │ - Read/Write 模式      │
│ - Scoped Decisions   │ │ - Workspace Lock       │
│ - Audit Log          │ │ - Git Worktree         │
└──────────────┬───────┘ └────────┬───────────────┘
               │                  │
┌──────────────▼──────────────────▼──────────────────────┐
│                    Backend Layer                      │
│                                                       │
│  AcpBackend                                           │
│    └─ grok agent stdio / grok agent serve             │
│                                                       │
│  HeadlessBackend                                      │
│    └─ grok -p --output-format streaming-json          │
└─────────────────────────┬─────────────────────────────┘
                          │
┌─────────────────────────▼─────────────────────────────┐
│                     Storage                          │
│                                                     │
│  SQLite WAL                                         │
│  - responses                                        │
│  - sessions                                         │
│  - events                                           │
│  - tool_calls                                       │
│  - permissions                                      │
│  - workspace_locks                                  │
│  - api_keys                                         │
│  - audit_logs                                       │
└─────────────────────────────────────────────────────┘
```

---

## 6. 核心组件设计

## 6.1 API Gateway

职责：

- 提供 HTTP 和 MCP 接口；
- 进行认证和 Scope 校验；
- 解析 OpenAI 标准字段；
- 解析 `x_grok` 扩展字段；
- 将请求交给 Response Orchestrator；
- 输出同步结果、SSE 或任务 ID。

不负责：

- 直接启动 Grok；
- 直接控制工作区；
- 直接做权限决策；
- 直接写事件记录。

### 6.1.1 标准字段与扩展字段

推荐请求：

```json
{
  "model": "grok-4.5",
  "input": "修复当前项目失败的单元测试",
  "stream": true,
  "background": false,
  "previous_response_id": null,
  "metadata": {
    "task": "fix-tests"
  },
  "x_grok": {
    "cwd": "/Users/me/projects/demo",
    "permission_policy": "ask",
    "workspace_mode": "worktree",
    "max_turns": 30,
    "sandbox": "workspace-write",
    "backend": "acp"
  }
}
```

规则：

- OpenAI 标准字段尽量保持标准语义；
- Grok 专属能力放入 `x_grok`；
- 旧 `/v1/chat/completions` 继续接受原有扩展字段；
- 内部统一转换为 `CreateResponseCommand`。

---

## 6.2 Response Orchestrator

这是整个系统的核心。

职责：

1. 创建 Response。
2. 选择 Backend。
3. 绑定 Grok Session。
4. 创建或分配工作区。
5. 运行状态机。
6. 接收 Backend 事件。
7. 将事件持久化。
8. 处理权限等待。
9. 处理取消和超时。
10. 生成最终结果。
11. 向 HTTP SSE 和 MCP 调用方广播事件。

接口建议：

```python
class ResponseOrchestrator:
    async def create(self, command: CreateResponseCommand) -> ResponseRecord: ...
    async def start(self, response_id: str) -> None: ...
    async def get(self, response_id: str) -> ResponseRecord: ...
    async def cancel(self, response_id: str, actor: Actor) -> ResponseRecord: ...
    async def stream_events(
        self,
        response_id: str,
        after_sequence: int = 0,
    ) -> AsyncIterator[ResponseEvent]: ...
```

---

## 6.3 Backend 抽象

```python
class GrokBackend(Protocol):
    async def start_session(
        self,
        request: BackendSessionRequest,
    ) -> BackendSession: ...

    async def send_prompt(
        self,
        session: BackendSession,
        prompt: PromptInput,
    ) -> None: ...

    async def events(
        self,
        session: BackendSession,
    ) -> AsyncIterator[BackendEvent]: ...

    async def resolve_permission(
        self,
        session: BackendSession,
        decision: PermissionDecision,
    ) -> None: ...

    async def cancel(
        self,
        session: BackendSession,
    ) -> None: ...

    async def close(
        self,
        session: BackendSession,
    ) -> None: ...
```

### 6.3.1 AcpBackend

主后端。

支持：

- Grok Session 创建；
- Prompt 发送；
- Tool Call；
- Tool Result；
- Permission Request；
- Plan；
- Text Delta；
- Usage；
- Cancel；
- Session Resume。

运行模式：

#### stdio 模式

每个活跃 Grok Session 对应一个本地子进程。

优点：

- 实现和部署简单；
- 故障隔离好；
- 不需要额外端口。

缺点：

- Session 多时进程较多。

#### serve 模式

代理连接长期运行的：

```text
grok agent serve
```

优点：

- 启动开销低；
- 适合多个客户端和长时间运行。

缺点：

- 连接管理更复杂；
- 需要服务发现和 Secret 管理。

建议：

- v0.3 先实现 stdio；
- v0.5 再支持 serve；
- Backend 配置可切换。

### 6.3.2 HeadlessBackend

保留现有 `GrokRunner`，但改造成 Backend：

- 使用 `--prompt-file` 代替 `-p` 长参数；
- 支持 `streaming-json`；
- 完整暴露 Tool、Plan、Usage；
- 不承担真正的交互审批；
- 适合只读、自动审批、CI 和回退场景。

---

## 7. Response API 设计

## 7.1 创建 Response

```http
POST /v1/responses
```

同步请求：

```json
{
  "model": "grok-4.5",
  "input": "分析当前项目架构",
  "stream": false,
  "background": false,
  "x_grok": {
    "cwd": "/repo",
    "workspace_mode": "read_only"
  }
}
```

后台请求：

```json
{
  "model": "grok-4.5",
  "input": "修复失败测试",
  "background": true,
  "x_grok": {
    "cwd": "/repo",
    "workspace_mode": "worktree",
    "permission_policy": "ask"
  }
}
```

后台响应：

```json
{
  "id": "resp_01J...",
  "object": "response",
  "status": "queued",
  "model": "grok-4.5",
  "created_at": 1785450000,
  "output": [],
  "x_grok": {
    "backend": "acp"
  }
}
```

## 7.2 查询 Response

```http
GET /v1/responses/{response_id}
```

返回：

- 状态；
- 输出；
- 工具调用摘要；
- 权限状态；
- Usage；
- 工作区信息；
- 错误信息。

## 7.3 取消 Response

```http
POST /v1/responses/{response_id}/cancel
```

取消应传播到：

- Orchestrator；
- ACP Session；
- Grok 进程；
- Shell 子进程；
- MCP Tool；
- 权限等待；
- Workspace Lock。

## 7.4 事件重放

```http
GET /v1/responses/{response_id}/events?after=37
```

支持：

```http
Last-Event-ID: 37
```

事件必须有：

```json
{
  "id": "evt_...",
  "response_id": "resp_...",
  "sequence_number": 38,
  "type": "response.output_text.delta",
  "created_at": 1785450001,
  "data": {}
}
```

---

## 8. Response 状态机

```text
queued
  │
  ▼
in_progress
  ├───────────────┐
  │               │
  ▼               ▼
waiting_for_approval
  │               │
  ├─ approved ────┘
  ├─ denied ──────┐
  └─ expired ─────┤
                  ▼
             in_progress
                  │
     ┌────────────┼─────────────┐
     ▼            ▼             ▼
 completed      failed       cancelled

另有：
incomplete
```

### 8.1 状态定义

| 状态 | 含义 |
|---|---|
| `queued` | 已创建，等待资源 |
| `in_progress` | Grok 正在执行 |
| `waiting_for_approval` | 等待权限决定 |
| `completed` | 正常完成 |
| `failed` | 系统、Backend 或 Grok 错误 |
| `cancelled` | 用户或系统取消 |
| `incomplete` | 达到 max_turns、超时或中断但保留部分结果 |

### 8.2 状态约束

- 终态不可重新进入运行态；
- `waiting_for_approval` 必须有至少一个 pending permission；
- 取消操作幂等；
- Permission Decision 必须幂等；
- 每次状态变化写入 Event Journal；
- 状态更新和事件写入应在同一事务中完成。

---

## 9. 事件模型

## 9.1 标准事件

建议至少支持：

```text
response.created
response.queued
response.in_progress
response.output_item.added
response.output_item.done
response.output_text.delta
response.output_text.done
response.completed
response.failed
response.cancelled
response.incomplete
```

## 9.2 Grok 扩展事件

```text
response.plan.updated
response.permission.required
response.permission.resolved
response.tool_call.started
response.tool_call.updated
response.tool_call.completed
response.tool_call.failed
response.workspace.created
response.workspace.changed
response.usage.updated
```

## 9.3 Grok 事件映射

| Grok / ACP 事件 | Gateway 事件 |
|---|---|
| Text delta | `response.output_text.delta` |
| Assistant message done | `response.output_text.done` |
| Tool call | `response.tool_call.started` |
| Tool update | `response.tool_call.updated` |
| Tool completed | `response.tool_call.completed` |
| Tool failed | `response.tool_call.failed` |
| Permission request | `response.permission.required` |
| Permission resolved | `response.permission.resolved` |
| Plan | `response.plan.updated` |
| Usage | `response.usage.updated` |
| Session end | `response.completed` |
| Backend error | `response.failed` |

---

## 10. Tool Call 设计

统一的 Tool Call 对象：

```json
{
  "id": "call_01J...",
  "response_id": "resp_01J...",
  "type": "shell_call",
  "name": "run_terminal_cmd",
  "status": "in_progress",
  "title": "Run pytest",
  "arguments": {
    "command": "pytest -q"
  },
  "result": null,
  "requires_approval": true,
  "started_at": 1785450001,
  "completed_at": null,
  "x_grok": {
    "raw_tool_name": "run_terminal_cmd",
    "kind": "execute"
  }
}
```

### 10.1 Tool 类型

建议规范化为：

- `shell_call`
- `read_file_call`
- `write_file_call`
- `apply_patch_call`
- `search_call`
- `web_call`
- `mcp_call`
- `subagent_call`
- `unknown_tool_call`

### 10.2 Tool Result

```json
{
  "stdout": "12 passed",
  "stderr": "",
  "exit_code": 0,
  "changed_files": [],
  "duration_ms": 3512,
  "truncated": false
}
```

### 10.3 输出限制

- stdout/stderr 需要长度上限；
- 超长结果写入 artifact 或日志文件；
- API 返回摘要和引用；
- 对凭据、Token、Cookie 做基础脱敏；
- 不公开原始内部 reasoning。

---

## 11. 权限系统

## 11.1 Permission Broker

职责：

1. 接收 ACP Permission Request。
2. 标准化操作类型。
3. 调用 Policy Engine。
4. 自动允许、自动拒绝或创建 Pending Permission。
5. 暂停对应 Response。
6. 接受审批决定。
7. 将决定返回 ACP Backend。
8. 写入审计日志。

```python
class PermissionBroker:
    async def evaluate(
        self,
        context: PermissionContext,
    ) -> PermissionEvaluation: ...

    async def decide(
        self,
        permission_id: str,
        command: DecidePermissionCommand,
    ) -> PermissionRecord: ...
```

## 11.2 权限请求对象

```json
{
  "id": "perm_01J...",
  "response_id": "resp_01J...",
  "tool_call_id": "call_01J...",
  "status": "pending",
  "category": "shell",
  "risk": "high",
  "title": "Execute shell command",
  "description": "Grok wants to delete build artifacts.",
  "arguments": {
    "command": "rm -rf build"
  },
  "cwd": "/repo",
  "options": [
    {
      "id": "allow_once",
      "label": "Allow once"
    },
    {
      "id": "allow_for_session",
      "label": "Allow similar operations for this session"
    },
    {
      "id": "deny_once",
      "label": "Deny"
    },
    {
      "id": "deny_with_feedback",
      "label": "Deny and give instructions"
    },
    {
      "id": "cancel_run",
      "label": "Cancel task"
    }
  ],
  "expires_at": "2026-07-31T11:00:00+08:00"
}
```

## 11.3 权限决策 API

```http
POST /v1/permissions/{permission_id}/decision
```

允许一次：

```json
{
  "decision": "allow_once"
}
```

会话授权：

```json
{
  "decision": "allow_for_session",
  "scope": {
    "type": "command_prefix",
    "value": "pytest"
  }
}
```

拒绝并反馈：

```json
{
  "decision": "deny_with_feedback",
  "feedback": "不要删除目录，只删除 build 目录中的临时文件。"
}
```

## 11.4 权限合并原则

最终权限：

```text
Server Hard Limit
  ∩ API Key Scope
  ∩ Workspace Policy
  ∩ Session Policy
  ∩ Request Policy
```

请求方只能收紧权限，不能扩大权限。

## 11.5 默认权限策略

| 操作 | 默认策略 |
|---|---|
| 读取工作区文件 | 自动允许 |
| grep/list/find | 自动允许 |
| 修改 Worktree 内文件 | 询问或按会话授权 |
| 修改原工作区 | 默认拒绝 |
| 运行测试 | 自动允许或首次询问 |
| 运行构建 | 首次询问 |
| 安装依赖 | 每次询问 |
| 网络访问 | 询问 |
| Git status/diff | 自动允许 |
| Git commit | 询问 |
| Git push | 必须询问 |
| 删除文件 | 必须询问 |
| 项目外路径读取 | 默认拒绝 |
| 凭据目录 | 硬拒绝 |
| sudo、系统配置 | 硬拒绝 |

## 11.6 配置示例

```yaml
policy:
  filesystem:
    read:
      auto_allow:
        - "${workspace}/**"
    write:
      ask:
        - "${run_workspace}/**"
      deny:
        - "~/.ssh/**"
        - "~/.aws/**"
        - "~/.config/**"
        - "/etc/**"

  shell:
    auto_allow:
      - "pytest *"
      - "npm test*"
      - "git status*"
      - "git diff*"
    ask:
      - "npm install*"
      - "pip install*"
      - "git commit*"
    deny:
      - "sudo *"
      - "git push --force*"
      - "rm -rf /*"

  network:
    default: ask
```

---

## 12. 工作区管理

## 12.1 Workspace Mode

支持：

- `read_only`
- `in_place`
- `worktree`
- `temporary_copy`

### `read_only`

- 适合分析、审查、架构梳理；
- 禁止写文件；
- 可并发。

### `in_place`

- 直接修改原目录；
- 风险最高；
- 默认关闭；
- 必须排他锁。

### `worktree`

- 推荐写任务默认模式；
- 每个 Response 独立 Git Worktree；
- 易于对比、回滚和审查；
- 支持并发写任务。

### `temporary_copy`

- 非 Git 项目使用；
- 创建临时副本；
- 任务结束输出差异。

## 12.2 Workspace Manager

职责：

- 解析并校验 cwd；
- 检查 allowlist；
- 选择运行目录；
- 创建 Worktree；
- 管理锁；
- 收集变更；
- 清理临时目录。

输出：

```json
{
  "source_cwd": "/repo",
  "run_cwd": "/repo/.grok-proxy/worktrees/resp_01J",
  "mode": "worktree",
  "branch": "grok/resp_01J",
  "changed_files": [
    "src/api.py",
    "tests/test_api.py"
  ]
}
```

## 12.3 锁策略

- 读任务：共享锁；
- 原目录写任务：排他锁；
- Worktree 写任务：源仓库元数据锁 + 独立工作区；
- 同一 Grok Session 不允许并发 Prompt；
- Session Resume 必须保持工作区一致。

---

## 13. 存储设计

第一阶段使用 SQLite WAL。

### 13.1 表结构

#### `responses`

```text
id
status
model
backend
input_json
output_json
metadata_json
x_grok_json
session_id
source_cwd
run_cwd
workspace_mode
created_at
started_at
completed_at
cancelled_at
last_sequence_number
error_code
error_message
```

#### `sessions`

```text
id
backend
backend_session_id
source_cwd
run_cwd
model
status
created_at
updated_at
last_response_id
```

#### `events`

```text
id
response_id
sequence_number
event_type
payload_json
created_at
```

唯一索引：

```text
(response_id, sequence_number)
```

#### `tool_calls`

```text
id
response_id
backend_tool_call_id
tool_type
tool_name
status
arguments_json
result_json
started_at
completed_at
```

#### `permissions`

```text
id
response_id
tool_call_id
status
category
risk
arguments_json
options_json
decision
decision_scope_json
feedback
requested_at
decided_at
expires_at
decided_by
```

#### `workspace_locks`

```text
workspace_key
lock_type
response_id
owner_id
acquired_at
expires_at
```

#### `api_keys`

```text
id
key_hash
name
scopes_json
workspace_allowlist_json
max_concurrent
max_runtime_sec
enabled
created_at
last_used_at
```

#### `audit_logs`

```text
id
actor_type
actor_id
action
resource_type
resource_id
payload_json
created_at
```

---

## 14. API Key 与权限范围

API Key 只保存 Hash。

建议格式：

```text
gp_live_<random>
gp_test_<random>
```

Scopes：

```text
response:create
response:read
response:cancel
event:read
permission:read
permission:approve
workspace:read
workspace:write
tool:read
tool:execute
admin:keys
```

示例：

```json
{
  "name": "codex-local",
  "workspaces": [
    "/Users/me/projects"
  ],
  "scopes": [
    "response:create",
    "response:read",
    "response:cancel",
    "event:read",
    "tool:read"
  ],
  "max_concurrent": 2,
  "max_runtime_sec": 1800
}
```

审批 Token 与任务 Token 应可分离。

---

## 15. MCP Server 设计

MCP 和 HTTP 必须共用 Orchestrator。

## 15.1 MCP Tools

### `grok_consult`

用途：

- 只读咨询；
- 架构分析；
- 方案比较；
- Bug 分析。

输入：

```json
{
  "prompt": "分析当前项目的并发问题",
  "cwd": "/repo",
  "max_turns": 10
}
```

默认：

- `workspace_mode=read_only`
- `permission_policy=server`
- 禁止写入。

### `grok_review`

用途：

- Code Review；
- 安全审查；
- Diff 审查。

输入：

```json
{
  "cwd": "/repo",
  "instructions": "审查当前未提交修改",
  "scope": "git_diff"
}
```

### `grok_delegate`

用途：

- 完整编码任务委派。

输入：

```json
{
  "prompt": "修复失败测试",
  "cwd": "/repo",
  "workspace_mode": "worktree",
  "permission_policy": "ask"
}
```

### `grok_resume`

```json
{
  "response_id": "resp_...",
  "prompt": "继续修复剩余问题"
}
```

### `grok_status`

```json
{
  "response_id": "resp_..."
}
```

### `grok_cancel`

```json
{
  "response_id": "resp_..."
}
```

### `grok_get_diff`

```json
{
  "response_id": "resp_..."
}
```

## 15.2 MCP 返回原则

- 短任务可以同步返回；
- 长任务返回 Response ID；
- Pending Permission 返回明确状态；
- 不把原始内部 reasoning 返回给主 Agent；
- 主 Agent 默认不能自行审批高风险操作，除非 Token 有 `permission:approve`。

---

## 16. Chat Completions 兼容层

保留：

```http
POST /v1/chat/completions
```

内部转换：

```text
ChatCompletionRequest
  └─ CreateResponseCommand
       └─ ResponseOrchestrator
```

限制：

- 不提供完整后台任务能力；
- 权限请求通过非标准 SSE 扩展或返回 `incomplete`；
- `session_id` 继续兼容；
- 推荐新客户端迁移到 `/v1/responses`。

兼容策略：

- `cwd` 等旧字段继续支持；
- 同时支持 `x_grok.cwd`；
- 发生冲突时 `x_grok` 优先；
- 返回中保留 `grok` 元数据；
- 新增 `response_id`。

---

## 17. Reasoning 与隐私

不向公开 API 输出原始 `thought`。

允许：

```json
{
  "reasoning": {
    "summary": "正在检查失败测试和相关代码路径。"
  }
}
```

开发调试模式：

```text
GROK_PROXY_DEBUG_RAW_EVENTS=false
```

即使启用：

- 仅写本机受限日志；
- 不通过普通 API 返回；
- 不持久化敏感凭据；
- 支持日志脱敏。

---

## 18. Usage 与成本

标准 Usage：

```json
{
  "input_tokens": 7210,
  "input_tokens_details": {
    "cached_tokens": 41000,
    "cache_creation_tokens": 0
  },
  "output_tokens": 1893,
  "output_tokens_details": {
    "reasoning_tokens": 412
  },
  "total_tokens": 50103
}
```

Grok 扩展：

```json
{
  "x_grok": {
    "usage": {
      "num_turns": 7,
      "model_usage": {
        "grok-4.5": {
          "model_calls": 7,
          "input_tokens": 7210,
          "output_tokens": 1893,
          "cached_tokens": 41000
        }
      },
      "total_cost_usd": 0.01268905,
      "usage_is_incomplete": false
    }
  }
}
```

---

## 19. 错误模型

统一错误：

```json
{
  "error": {
    "message": "Workspace is not allowed",
    "type": "invalid_request_error",
    "code": "workspace_forbidden",
    "param": "x_grok.cwd",
    "request_id": "req_..."
  }
}
```

错误分类：

- `authentication_error`
- `authorization_error`
- `invalid_request_error`
- `conflict_error`
- `rate_limit_error`
- `backend_error`
- `timeout_error`
- `cancelled_error`
- `permission_error`
- `workspace_error`

关键错误码：

```text
invalid_cwd
workspace_forbidden
workspace_locked
session_cwd_mismatch
permission_required
permission_expired
permission_already_decided
backend_unavailable
backend_protocol_error
grok_auth_failed
grok_timeout
response_cancelled
response_terminal
event_sequence_conflict
```

---

## 20. 进程与取消管理

### 20.1 Process Manager

记录：

- PID；
- 进程组；
- Response ID；
- Session ID；
- Backend；
- 启动时间；
- 最后心跳；
- 当前状态。

### 20.2 取消顺序

1. 标记 `cancellation_requested`；
2. 通知 Backend；
3. 取消 Pending Permission；
4. 终止 Shell 子进程；
5. 终止 Grok Session；
6. 等待 Grace Period；
7. 强制 Kill；
8. 释放 Workspace Lock；
9. 写入 `response.cancelled`；
10. 保留已产生输出。

### 20.3 断线

- SSE 断线不自动取消任务；
- 同步请求可配置：
  - `cancel_on_disconnect=true`
  - 默认 `false`；
- 后台任务不依赖 HTTP 连接；
- 服务重启后恢复可恢复任务，无法恢复的标记为 `incomplete`。

---

## 21. 代码结构重构

```text
src/grok_proxy/
├── api/
│   ├── dependencies.py
│   ├── chat_completions.py
│   ├── responses.py
│   ├── permissions.py
│   ├── models.py
│   ├── events.py
│   └── health.py
├── auth/
│   ├── api_keys.py
│   ├── scopes.py
│   └── actors.py
├── backends/
│   ├── base.py
│   ├── headless.py
│   ├── acp.py
│   ├── acp_client.py
│   └── models.py
├── runtime/
│   ├── orchestrator.py
│   ├── state_machine.py
│   ├── process_manager.py
│   ├── cancellation.py
│   ├── event_bus.py
│   └── commands.py
├── permissions/
│   ├── broker.py
│   ├── policy.py
│   ├── matcher.py
│   ├── models.py
│   └── audit.py
├── workspace/
│   ├── manager.py
│   ├── locks.py
│   ├── worktree.py
│   ├── diff.py
│   └── models.py
├── protocol/
│   ├── responses_models.py
│   ├── chat_models.py
│   ├── event_mapper.py
│   ├── tool_mapper.py
│   └── grok_extensions.py
├── storage/
│   ├── database.py
│   ├── migrations.py
│   ├── repositories/
│   │   ├── responses.py
│   │   ├── sessions.py
│   │   ├── events.py
│   │   ├── permissions.py
│   │   └── api_keys.py
│   └── models.py
├── mcp/
│   ├── server.py
│   ├── tools.py
│   └── schemas.py
├── config.py
├── main.py
└── __main__.py
```

---

## 22. 配置设计

```yaml
server:
  host: 127.0.0.1
  port: 8787
  database_url: sqlite:///~/.grok-proxy/gateway.db

backend:
  default: acp
  acp:
    mode: stdio
    grok_bin: grok
  headless:
    enabled: true

responses:
  max_concurrent: 2
  default_timeout_sec: 1800
  permission_timeout_sec: 900
  event_retention_days: 30

workspace:
  allowlist:
    - ~/projects
  default_mode: worktree
  allow_in_place: false
  cleanup_completed_after_hours: 24

security:
  require_auth: true
  expose_raw_thoughts: false
  redact_secrets: true

mcp:
  enabled: true
  transport: stdio
```

环境变量继续支持，并映射到分层配置。

---

## 23. 测试策略

## 23.1 单元测试

覆盖：

- 状态机；
- Scope；
- Policy Matcher；
- 工作区路径校验；
- Worktree；
- Tool 映射；
- ACP 事件映射；
- Permission Decision；
- Usage 映射；
- 错误映射；
- API 模型校验。

## 23.2 集成测试

使用 Fake ACP Server，模拟：

- 文本流；
- Tool Call；
- Permission Request；
- Permission Approve；
- Permission Reject；
- Tool Failure；
- Cancel；
- Session Resume；
- 断线重连；
- Backend 崩溃。

## 23.3 Grok CLI E2E

可选测试标签：

```text
pytest -m grok_e2e
```

验证：

- `grok agent stdio` 可连接；
- 创建 Session；
- 只读分析；
- 文件编辑权限；
- Shell 权限；
- Session Resume；
- Cancel；
- Worktree；
- Usage；
- OAuth 登录模式。

CI 默认不执行需要真实账号的 E2E。

## 23.4 客户端兼容测试

- OpenAI Python SDK；
- curl；
- WorkBuddy 自定义模型；
- MCP Inspector；
- Codex MCP；
- Qoder MCP；
- CodeBuddy MCP。

---

## 24. 可观测性

### 24.1 日志

字段：

```text
request_id
response_id
session_id
tool_call_id
permission_id
api_key_id
workspace
backend
event_type
duration_ms
```

### 24.2 Metrics

```text
responses_total
responses_active
responses_duration_seconds
responses_by_status
permissions_pending
permissions_decision_seconds
tool_calls_total
tool_calls_failed
backend_restarts_total
workspace_locks_active
sse_connections_active
```

### 24.3 Health

```http
GET /health
GET /ready
GET /v1/health
```

`ready` 应检查：

- 数据库；
- Grok 二进制；
- ACP Backend；
- Workspace 根目录；
- 模型探测。

---

## 25. 安全设计

### 25.1 本地默认

- 默认监听 `127.0.0.1`；
- 默认必须认证；
- Key 文件权限 `0600`；
- 状态目录 `0700`；
- 禁止默认公网暴露；
- 不默认启用 `in_place`；
- 不默认 `always_approve`。

### 25.2 远程部署

必须增加：

- TLS；
- 反向代理；
- 身份认证；
- Scoped API Key；
- 容器或系统用户隔离；
- 工作区挂载隔离；
- 审批者身份；
- 日志脱敏；
- 访问审计。

### 25.3 硬拒绝

任何客户端都不能覆盖：

- 系统路径 deny；
- 凭据目录 deny；
- `sudo` deny；
- API Key Scope；
- Workspace Allowlist；
- 最大运行时间；
- 最大并发；
- 最大输出大小。

---

## 26. 迁移策略

### 阶段 1：抽象现有代码

- 将当前 `GrokRunner` 包装为 `HeadlessBackend`；
- 将 Chat API 改为调用 Orchestrator；
- 行为保持兼容。

### 阶段 2：引入持久化 Response

- 新建 SQLite；
- 新增 `/v1/responses`；
- 新增事件表；
- 新增取消和查询。

### 阶段 3：接入 ACP

- 实现 ACP Client；
- 建立 `AcpBackend`；
- 输出 Tool 和 Plan 事件；
- 保留 Headless 回退。

### 阶段 4：权限闭环

- Permission Broker；
- Policy Engine；
- Approval API；
- 状态机暂停与恢复。

### 阶段 5：工作区隔离

- Worktree；
- 锁；
- Diff；
- 清理。

### 阶段 6：MCP

- MCP Server；
- Codex/Qoder/CodeBuddy 接入；
- 权限 Scope。

---

## 27. 版本路线

### v0.2：Stateful Responses

目标：

- `/v1/responses`
- 持久化 Response
- 状态查询
- SSE 重连
- 工具事件
- 取消
- HeadlessBackend 抽象

### v0.3：ACP 与权限

目标：

- ACP stdio Backend
- Permission Broker
- Policy Engine
- Approval API
- Session Resume
- Graceful Cancel

### v0.4：Workspace Isolation

目标：

- Worktree
- Workspace Lock
- Diff
- Scoped API Key
- Audit Log
- Secret Redaction

### v0.5：MCP Agent Gateway

目标：

- MCP stdio
- MCP Streamable HTTP
- grok_consult
- grok_review
- grok_delegate
- grok_resume
- grok_status
- grok_cancel
- grok_get_diff

### v0.6：Remote / Multi-user

目标：

- PostgreSQL
- 多 Worker
- Redis/Event Bus
- 容器隔离
- Remote ACP Serve
- 管理接口
- 用户和审批者分离

---

## 28. 验收标准

项目达到“接近真实模型 API”应满足：

1. 调用方能创建一个有唯一 ID 的 Agent 任务。
2. 调用方能看到文本、计划、工具调用和工具结果。
3. 高风险操作可以暂停并等待审批。
4. 审批后 Grok 可以继续原 Session。
5. 客户端断线后可以重新订阅事件。
6. 任务可以后台运行。
7. 任务可以被可靠取消。
8. 服务重启后可以查询历史任务。
9. 写任务默认在独立 Worktree 中执行。
10. 调用 Token 不能突破服务器权限上限。
11. Codex/Qoder/CodeBuddy 能通过 MCP 调用 Grok。
12. WorkBuddy 和 OpenAI SDK 仍可通过 HTTP 使用。
13. 不暴露原始内部 reasoning。
14. 有真实 Grok CLI E2E 测试。
15. 权限和工具执行有完整审计记录。

---

## 29. 推荐优先级

第一优先级：

- Backend 抽象；
- Response 状态机；
- SQLite Event Journal；
- `/v1/responses`；
- 取消和事件重连。

第二优先级：

- ACP Backend；
- Tool Event；
- Permission Broker；
- Approval API。

第三优先级：

- Worktree；
- Scoped API Key；
- MCP Server。

不建议最先做：

- Web 管理 UI；
- 多租户；
- PostgreSQL；
- 容器平台；
- 完整 Responses API 字段复制。

---

## 30. 最终结论

推荐将项目定位为：

> A local OpenAI-compatible and MCP-accessible gateway for Grok Build, with stateful agent runs, tool visibility, human-in-the-loop permissions, workspace isolation and session persistence.

最关键的技术决策：

1. 内部主路径由 `grok -p` 切换为 ACP Runtime。
2. 对外主协议由 Chat Completions 扩展为 Responses API。
3. 工具执行和权限审批成为一等事件。
4. MCP 与 HTTP 复用同一 Orchestrator。
5. 所有权限由服务器设置上限，客户端只能收紧。
6. 写任务默认使用 Git Worktree。
7. HeadlessBackend 保留为兼容与故障回退路径。
