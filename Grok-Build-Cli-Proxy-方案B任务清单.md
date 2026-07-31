<!--
状态：v0.2 代码对账（2026-07-31）
- last reconciled: 2026-07-31
- 本轮按 `src/grok_proxy/` 与 tests/docs 实际实现核对；此前部分批量勾选可能偏乐观，本清单以代码为准。
- v0.2 基础路径已落地：Backend/Headless/SQLite/状态机/Responses+SSE/cancel/ACP 基础/权限 broker+API/workspace/scoped keys/MCP tools 基础/metrics/request_id/per-key 并发等。
- 未完成：pre-commit、客户端 E2E（Codex/WorkBuddy 等）、完整 ACP 工具/权限 E2E、agent serve、DELETE/list responses、正式重启恢复（pid reclaim 已有基础）、客户端/ACP 全量 E2E、标准 MCP SDK、Docker 等。
-->

# Grok Build CLI Proxy：方案 B 实施任务清单

## 1. 使用说明

本清单对应《Grok Build CLI Proxy：方案 B 完整优化设计》。

任务状态标记：

- `[ ]` 未开始
- `[-]` 进行中
- `[x]` 已完成
- `[!]` 阻塞
- `[~]` 暂缓

优先级：

- `P0`：主链路必须完成
- `P1`：正式可用必须完成
- `P2`：增强能力
- `P3`：后续版本

---

# 2. Milestone 0：基线确认与架构准备

## 2.1 项目基线

- [x] `P0` 固定当前 v0.1 行为基线
  - 验收：现有 `/v1/chat/completions`、SSE、WorkBuddy 配置、模型探测测试全部通过
- [x] `P0` 增加版本兼容矩阵
  - Grok CLI 版本
  - Python 版本
  - OpenAI SDK 版本
  - WorkBuddy 版本
- [x] `P0` 增加 ADR：为什么选择 ACP Runtime + Responses API
- [x] `P0` 记录当前 API 契约快照
- [x] `P1` 增加项目架构图
- [x] `P1` 增加风险清单

## 2.2 开发规范

- [x] `P0` 引入格式化、Lint 和类型检查
  - Ruff
  - Pyright 或 Mypy
- [x] `P0` 建立测试分类
  - unit
  - integration
  - grok_e2e
  - client_compat
- [x] `P0` 增加 CI
  - lint
  - typecheck
  - unit tests
  - integration tests
- [ ] `P1` 增加 pre-commit
- [ ] `P1` 增加 changelog 规范

---

# 3. Milestone 1：Backend 抽象与现有功能迁移

## 3.1 Backend 接口

- [x] `P0` 新建 `backends/base.py`
- [x] `P0` 定义 `GrokBackend` Protocol
- [x] `P0` 定义 `BackendSession`
- [x] `P0` 定义 `BackendEvent`
- [x] `P0` 定义 `BackendSessionRequest`
- [x] `P0` 定义 `BackendError`
- [x] `P0` 定义 `BackendCapabilities`

验收：

- Chat API 不直接依赖 `GrokRunner`
- Orchestrator 可按配置选择 Backend
- 单元测试可使用 FakeBackend

## 3.2 HeadlessBackend

- [x] `P0` 将现有 `GrokRunner` 包装为 `HeadlessBackend`
- [x] `P0` 将长 Prompt 改为 `--prompt-file`
- [x] `P0` 临时 Prompt 文件权限设置为 `0600`
- [x] `P0` 支持客户端取消时终止进程
- [x] `P0` 捕获 `asyncio.CancelledError`
- [x] `P0` 确保终止整个进程组
- [x] `P0` 完整解析 `streaming-json`
- [x] `P0` 保留 Text 事件
- [x] `P0` 增加 Tool Call 事件
- [x] `P0` 增加 Tool Update 事件
- [x] `P0` 增加 Plan 事件
- [x] `P0` 增加 Usage 事件
- [x] `P0` 增加 End/Error 事件
- [x] `P1` 增加输出大小限制
- [x] `P1` 增加 stderr 脱敏
- [ ] `P1` 增加模型能力探测

验收：

- 现有 Chat API 功能不退化
- HeadlessBackend 可独立运行
- 所有 Grok 事件均有内部对象表示
- 不再通过命令行参数暴露完整 Prompt

---

# 4. Milestone 2：状态机与持久化

## 4.1 SQLite

- [x] `P0` 引入 SQLite WAL
- [x] `P0` 新建数据库初始化模块
- [x] `P0` 新建迁移机制
- [x] `P0` 创建 `responses` 表
- [x] `P0` 创建 `sessions` 表
- [x] `P0` 创建 `events` 表
- [x] `P0` 创建 `tool_calls` 表
- [x] `P0` 创建 `permissions` 表
- [x] `P1` 创建 `workspace_locks` 表
- [x] `P1` 创建 `api_keys` 表
- [x] `P1` 创建 `audit_logs` 表
- [x] `P0` 为 Event Sequence 建立唯一索引
- [x] `P0` 增加事务封装

验收：

- 服务重启后历史 Response 可查询
- Event Sequence 不重复
- 状态更新和事件写入原子化

## 4.2 Response 状态机

- [x] `P0` 定义 Response 状态枚举
- [x] `P0` 定义合法状态迁移
- [x] `P0` 拒绝非法状态迁移
- [x] `P0` 定义终态
- [x] `P0` 定义 `waiting_for_approval`
- [x] `P0` 定义 `incomplete`
- [x] `P0` 增加状态迁移事件
- [x] `P0` 增加状态机单元测试
- [ ] `P1` 增加超时状态迁移
- [ ] `P1` 增加服务重启后的任务恢复规则

验收：

- 所有状态变更可审计
- 终态不可恢复执行
- 取消操作幂等
- 权限等待状态有严格约束

## 4.3 Event Journal

- [x] `P0` 定义统一 `ResponseEvent`
- [x] `P0` 实现事件持久化
- [x] `P0` 实现事件序列号
- [x] `P0` 实现按 `after_sequence` 查询
- [x] `P0` 实现实时事件广播
- [ ] `P1` 实现事件保留策略
- [ ] `P1` 实现超长 Payload 外置
- [ ] `P1` 实现日志脱敏

验收：

- 客户端断线后可重放遗漏事件
- 事件顺序稳定
- 同一 Response 不丢事件

---

# 5. Milestone 3：Response Orchestrator

## 5.1 Orchestrator 核心

- [x] `P0` 新建 `ResponseOrchestrator`
- [x] `P0` 实现 `create`
- [x] `P0` 实现 `start`
- [x] `P0` 实现 `get`
- [x] `P0` 实现 `cancel`
- [x] `P0` 实现 `stream_events`
- [x] `P0` 实现 Backend 选择
- [x] `P0` 实现 Session 绑定
- [x] `P0` 实现事件消费循环
- [x] `P0` 实现最终输出聚合
- [x] `P0` 实现错误转换
- [x] `P0` 实现超时
- [x] `P0` 实现清理逻辑
- [x] `P1` 实现 Background Task
- [x] `P1` 实现任务并发控制
- [x] `P1` 实现 per-key 并发限制

验收：

- FakeBackend 可跑通完整 Response
- Response 可以同步或后台执行
- 取消后 Backend 和状态均正确
- Backend 崩溃后 Response 标记失败

## 5.2 Process Manager

- [x] `P0` 记录 Grok 子进程
- [x] `P0` 记录进程组
- [x] `P0` 实现 Graceful Stop
- [x] `P0` 实现 Force Kill
- [x] `P0` 实现取消传播
- [ ] `P1` 实现孤儿进程扫描
- [ ] `P1` 实现服务启动时残留任务处理
- [ ] `P2` 实现进程心跳

验收：

- 超时、取消、客户端断开均不残留子进程
- 服务关闭时清理活跃进程

---

# 6. Milestone 4：`/v1/responses`

## 6.1 数据模型

- [x] `P0` 定义 `CreateResponseRequest`
- [x] `P0` 定义 `ResponseObject`
- [x] `P0` 定义 `ResponseOutputItem`
- [x] `P0` 定义 `ResponseUsage`
- [x] `P0` 定义 `ResponseError`
- [x] `P0` 定义 `GrokExtensions`
- [x] `P0` 定义输入 Text 和 Message
- [ ] `P1` 定义工具输出对象
- [ ] `P1` 定义 Reasoning Summary

## 6.2 API

- [x] `P0` 实现 `POST /v1/responses`
- [x] `P0` 实现 `GET /v1/responses/{id}`
- [x] `P0` 实现 `POST /v1/responses/{id}/cancel`
- [x] `P0` 实现 `GET /v1/responses/{id}/events`
- [x] `P0` 实现 SSE
- [x] `P0` 支持 `Last-Event-ID`
- [x] `P0` 支持 `background`
- [x] `P0` 支持 `stream`
- [x] `P0` 支持 `previous_response_id`
- [x] `P0` 支持 `metadata`
- [x] `P0` 支持 `x_grok`
- [ ] `P1` 实现 `DELETE /v1/responses/{id}`
- [ ] `P1` 增加分页查询接口
- [ ] `P1` 增加任务列表接口

验收：

- OpenAI SDK 可调用基本 Response
- SSE 可重连
- 后台任务可查询、取消
- `x_grok` 参数不污染标准字段

---

# 7. Milestone 5：Chat Completions 兼容层重构

- [x] `P0` 将 Chat API 转换为 `CreateResponseCommand`
- [x] `P0` 保留原有 `cwd`
- [x] `P0` 保留 `session_id`
- [x] `P0` 保留 `max_turns`
- [x] `P0` 保留 `sandbox`
- [x] `P0` 保留 `worktree`
- [x] `P0` 支持 `x_grok`
- [x] `P0` 冲突时 `x_grok` 优先
- [x] `P0` 返回 `response_id`
- [x] `P0` 保留原 `grok` 元数据
- [x] `P0` 保持 OpenAI SSE 基本兼容
- [ ] `P1` 对权限等待返回清晰扩展事件
- [x] `P1` 更新 README 迁移说明

验收：

- v0.1 客户端不修改配置仍可使用
- Chat 与 Responses 共用同一执行链路

---

# 8. Milestone 6：ACP Backend

## 8.1 ACP Client 基础

- [ ] `P0` 调研并固定 ACP SDK 版本
- [x] `P0` 实现 JSON-RPC stdio transport
- [x] `P0` 实现初始化握手
- [x] `P0` 实现 Session 创建
- [x] `P0` 实现 Prompt 发送
- [x] `P0` 实现 Session Update 监听
- [x] `P0` 实现 Session Cancel
- [x] `P0` 实现 Session Close
- [x] `P0` 实现协议错误处理
- [x] `P0` 实现 stdout/stderr 分离
- [ ] `P1` 实现进程重启
- [ ] `P1` 实现 ACP 能力探测

## 8.2 ACP 事件映射

- [x] `P0` 映射 Text
- [x] `P0` 映射 Tool Call
- [x] `P0` 映射 Tool Update
- [x] `P0` 映射 Tool Result
- [x] `P0` 映射 Plan
- [x] `P0` 映射 Usage
- [x] `P0` 映射 Permission Request
- [x] `P0` 映射 Session End
- [x] `P0` 映射 Error
- [ ] `P1` 映射 Subagent
- [ ] `P1` 映射 Available Commands
- [ ] `P1` 保留 Raw Event 调试能力

## 8.3 AcpBackend

- [x] `P0` 实现 `AcpBackend.start_session`
- [x] `P0` 实现 `send_prompt`
- [x] `P0` 实现 `events`
- [x] `P0` 实现 `resolve_permission`
- [x] `P0` 实现 `cancel`
- [x] `P0` 实现 `close`
- [ ] `P0` 支持 Session Resume
- [x] `P0` 绑定 cwd
- [ ] `P0` 绑定 model
- [x] `P0` 绑定 permission mode
- [ ] `P1` 支持 `grok agent serve`
- [x] `P1` 支持 backend failover

验收：

- 无 `--always-approve` 时可正常收到权限请求
- 审批后 Grok 在原 Session 中继续
- 工具事件完整可见
- Cancel 可终止 ACP Session

---

# 9. Milestone 7：Permission Broker

## 9.1 权限模型

- [x] `P0` 定义 Permission 状态
- [x] `P0` 定义 Permission Category
- [x] `P0` 定义 Risk Level
- [x] `P0` 定义 Decision
- [x] `P0` 定义 Scope
- [x] `P0` 定义 Expiration
- [x] `P0` 定义 Decision Actor

## 9.2 Policy Engine

- [x] `P0` 定义硬拒绝规则
- [x] `P0` 定义自动允许规则
- [x] `P0` 定义询问规则
- [x] `P0` 实现路径匹配
- [x] `P0` 实现 Shell 命令匹配
- [x] `P0` 实现 MCP Tool 匹配
- [x] `P0` 实现网络域名匹配
- [x] `P0` 实现 Deny 优先
- [ ] `P0` 实现客户端只能收紧权限
- [ ] `P1` 支持 YAML 配置
- [ ] `P1` 支持配置热重载
- [ ] `P1` 支持风险评分

## 9.3 Permission Broker

- [x] `P0` 接收 ACP Permission Request
- [x] `P0` 调用 Policy Engine
- [x] `P0` 自动允许
- [x] `P0` 自动拒绝
- [x] `P0` 创建 Pending Permission
- [x] `P0` 将 Response 置为等待审批
- [x] `P0` 权限过期
- [x] `P0` 权限决定幂等
- [x] `P0` 将决定返回 ACP
- [x] `P0` 审批后恢复 Response
- [x] `P0` 拒绝后向 Grok 传递反馈
- [ ] `P1` 支持会话范围授权
- [ ] `P1` 支持命令前缀授权
- [ ] `P1` 支持 MCP Server 范围授权
- [ ] `P1` 支持域名范围授权

## 9.4 Approval API

- [x] `P0` 实现 `GET /v1/permissions/{id}`
- [x] `P0` 实现 `POST /v1/permissions/{id}/decision`
- [x] `P0` 校验审批 Scope
- [x] `P0` 校验审批者权限
- [x] `P0` 实现 `allow_once`
- [x] `P0` 实现 `allow_for_session`
- [x] `P0` 实现 `deny_once`
- [x] `P0` 实现 `deny_with_feedback`
- [x] `P0` 实现 `cancel_run`
- [x] `P1` 实现 Pending Permission 列表
- [x] `P1` 实现批量拒绝

验收：

- 高风险命令可暂停
- 审批者与任务发起者可使用不同 Token
- 重复审批不会产生二次执行
- 过期审批被拒绝
- 所有权限决定写审计日志

---

# 10. Milestone 8：Workspace Manager

## 10.1 基础

- [x] `P0` 实现 cwd 解析
- [x] `P0` 实现真实路径解析
- [x] `P0` 防止符号链接逃逸
- [x] `P0` 实现 Workspace Allowlist
- [x] `P0` 实现 `read_only`
- [x] `P0` 实现 `in_place`
- [x] `P0` 默认禁止 `in_place`
- [x] `P1` 实现 `temporary_copy`

## 10.2 Git Worktree

- [x] `P0` 检测 Git 仓库
- [x] `P0` 创建 Worktree
- [x] `P0` 创建任务分支
- [x] `P0` 记录 source/run cwd
- [x] `P0` 收集 changed files
- [x] `P0` 生成 diff
- [x] `P0` 清理 Worktree
- [ ] `P0` 失败时保留诊断信息
- [ ] `P1` 支持 base ref
- [ ] `P1` 支持保留 Worktree
- [ ] `P1` 支持冲突检测

## 10.3 Workspace Lock

- [x] `P0` 实现共享读锁
- [x] `P0` 实现排他写锁
- [ ] `P0` 实现锁超时
- [ ] `P0` 实现崩溃后锁恢复
- [ ] `P0` 实现 Session 串行化
- [ ] `P1` 实现锁等待队列
- [ ] `P1` 实现锁状态 API

验收：

- 两个写任务不会修改同一原工作区
- Worktree 任务可并行
- Session Resume 使用同一运行目录
- 任务完成后可获取 Diff

---

# 11. Milestone 9：Scoped API Key

## 11.1 Key 管理

- [x] `P0` Key 只存 Hash
- [x] `P0` 支持 `gp_live_` 和 `gp_test_`
- [x] `P0` 支持 Key 名称
- [x] `P0` 支持启停
- [x] `P0` 支持撤销
- [x] `P0` 支持最后使用时间
- [ ] `P1` 支持 Key 轮换
- [ ] `P1` 支持过期时间

## 11.2 Scopes

- [x] `P0` 实现 `response:create`
- [x] `P0` 实现 `response:read`
- [x] `P0` 实现 `response:cancel`
- [x] `P0` 实现 `event:read`
- [x] `P0` 实现 `permission:read`
- [x] `P0` 实现 `permission:approve`
- [x] `P0` 实现 `workspace:read`
- [x] `P0` 实现 `workspace:write`
- [x] `P0` 实现 `tool:execute`
- [x] `P1` 实现管理 Scope

## 11.3 限制

- [x] `P0` per-key workspace allowlist
- [x] `P0` per-key max concurrent
- [x] `P0` per-key max runtime
- [x] `P0` per-key workspace mode
- [x] `P0` per-key tool capability
- [ ] `P1` per-key rate limit

验收：

- 无审批 Scope 的 Agent 无法批准自己
- Key 无法访问 Allowlist 外项目
- Key 无法突破服务端硬限制

---

# 12. Milestone 10：MCP Server

## 12.1 基础

- [ ] `P0` 选择 MCP SDK
- [x] `P0` 实现 MCP stdio
- [ ] `P1` 实现 Streamable HTTP
- [ ] `P0` MCP 与 HTTP 共用认证上下文
- [x] `P0` MCP 与 HTTP 共用 Orchestrator
- [x] `P0` MCP 错误映射

## 12.2 Tools

- [x] `P0` 实现 `grok_consult`
- [x] `P0` 实现 `grok_review`
- [x] `P0` 实现 `grok_delegate`
- [x] `P0` 实现 `grok_resume`
- [x] `P0` 实现 `grok_status`
- [x] `P0` 实现 `grok_cancel`
- [x] `P0` 实现 `grok_get_diff`
- [ ] `P1` 实现 `grok_get_events`
- [ ] `P1` 实现 `grok_list_permissions`

## 12.3 默认策略

- [x] `P0` `grok_consult` 强制只读
- [x] `P0` `grok_review` 默认只读
- [x] `P0` `grok_delegate` 默认 Worktree
- [ ] `P0` MCP 调用方默认无审批权
- [x] `P0` 长任务返回 Response ID
- [ ] `P1` 支持同步等待上限

## 12.4 客户端验证

- [ ] `P0` MCP Inspector
- [ ] `P0` Codex MCP
- [ ] `P0` Qoder MCP
- [ ] `P0` CodeBuddy MCP
- [ ] `P1` Pi Agent MCP
- [ ] `P1` OpenCode MCP

验收：

- Codex 可调用 `grok_review`
- Qoder 可调用 `grok_delegate`
- 主 Agent 可查询状态和获取 Diff
- 高风险权限不会被主 Agent 自动放行

---

# 13. Milestone 11：Reasoning、Usage 与输出治理

## 13.1 Reasoning

- [x] `P0` 默认不输出原始 thought
- [ ] `P0` 增加 Reasoning Summary
- [ ] `P0` 删除 `include_thoughts` 公共能力或标记废弃
- [ ] `P1` 增加 Debug Raw Event 开关
- [ ] `P1` Raw Event 仅本机可用
- [ ] `P1` Raw Event 不写普通 API

## 13.2 Usage

- [x] `P0` 映射 input tokens
- [x] `P0` 映射 output tokens
- [x] `P0` 映射 cached tokens
- [ ] `P0` 映射 cache creation tokens
- [x] `P0` 映射 reasoning tokens
- [x] `P0` 映射 num_turns
- [ ] `P0` 映射 model usage
- [ ] `P0` 映射 cost
- [x] `P0` 处理 incomplete usage
- [ ] `P1` 增加 Usage 聚合 API

## 13.3 输出治理

- [x] `P0` stdout/stderr 大小限制
- [ ] `P0` Tool Result 截断标记
- [x] `P0` Secret Redaction
- [x] `P0` API Key Redaction
- [ ] `P0` Cookie Redaction
- [ ] `P1` 超大输出外置
- [ ] `P1` Artifact 下载授权

---

# 14. Milestone 12：可观测性

## 14.1 日志

- [x] `P0` 结构化日志
- [x] `P0` request_id
- [x] `P0` response_id
- [ ] `P0` session_id
- [ ] `P0` tool_call_id
- [ ] `P0` permission_id
- [x] `P0` api_key_id
- [ ] `P0` backend
- [x] `P0` duration
- [ ] `P0` 日志脱敏

## 14.2 Metrics

- [x] `P1` `responses_total`
- [x] `P1` `responses_active`
- [x] `P1` `responses_duration_seconds`
- [ ] `P1` `permissions_pending`
- [ ] `P1` `permissions_decision_seconds`
- [ ] `P1` `tool_calls_total`
- [ ] `P1` `tool_calls_failed`
- [ ] `P1` `backend_restarts_total`
- [ ] `P1` `workspace_locks_active`
- [x] `P1` `sse_connections_active`

## 14.3 Health

- [x] `P0` `/health`
- [x] `P0` `/ready`
- [x] `P0` 数据库检查
- [ ] `P0` Grok Binary 检查
- [ ] `P0` ACP Backend 检查
- [ ] `P0` Workspace 检查
- [ ] `P0` 模型探测检查

---

# 15. Milestone 13：测试

## 15.1 Unit

- [x] `P0` 状态机测试
- [x] `P0` Policy Matcher 测试
- [x] `P0` Scope 测试
- [x] `P0` Workspace 路径测试
- [x] `P0` 符号链接逃逸测试
- [ ] `P0` Worktree 测试
- [x] `P0` Tool Mapper 测试
- [x] `P0` ACP Event Mapper 测试
- [x] `P0` Permission Broker 测试
- [ ] `P0` Usage Mapper 测试
- [ ] `P0` Error Mapper 测试

## 15.2 Integration

- [x] `P0` Fake ACP 文本流
- [ ] `P0` Fake ACP Tool Call
- [ ] `P0` Fake ACP Permission
- [ ] `P0` Approve 后继续
- [ ] `P0` Reject 后继续
- [ ] `P0` Permission 超时
- [x] `P0` Cancel
- [ ] `P0` Backend 崩溃
- [x] `P0` SSE 重连
- [ ] `P0` 服务重启恢复
- [ ] `P0` Workspace Lock
- [ ] `P0` Worktree Diff

## 15.3 Grok E2E

- [ ] `P1` 真实 `grok agent stdio`
- [ ] `P1` 真实只读任务
- [ ] `P1` 真实文件编辑
- [ ] `P1` 真实 Shell 权限
- [ ] `P1` 真实拒绝并反馈
- [ ] `P1` 真实 Session Resume
- [x] `P1` 真实 Cancel
- [ ] `P1` 真实 Usage
- [ ] `P1` OAuth 登录
- [ ] `P2` API Key 登录
- [ ] `P2` `agent serve`

## 15.4 Client Compatibility

- [ ] `P0` curl
- [ ] `P0` OpenAI Python SDK
- [ ] `P0` WorkBuddy
- [ ] `P0` MCP Inspector
- [ ] `P0` Codex
- [ ] `P0` Qoder
- [ ] `P0` CodeBuddy

---

# 16. Milestone 14：文档与发布

## 16.1 文档

- [x] `P0` 更新 README
- [ ] `P0` Responses API 文档
- [ ] `P0` Permission API 文档
- [ ] `P0` MCP 文档
- [ ] `P0` WorkBuddy 配置
- [ ] `P0` Codex 配置
- [ ] `P0` Qoder 配置
- [ ] `P0` CodeBuddy 配置
- [x] `P0` 安全说明
- [ ] `P0` 权限策略说明
- [ ] `P0` Worktree 说明
- [ ] `P1` 故障排查
- [x] `P1` 架构图
- [ ] `P1` API 示例集合

## 16.2 发布

- [x] `P0` v0.2 Release Notes
- [ ] `P0` v0.3 Release Notes
- [x] `P0` 升级指南
- [ ] `P0` 数据库迁移说明
- [ ] `P0` 配置迁移说明
- [ ] `P1` Dockerfile
- [ ] `P1` Homebrew 或 pipx 安装说明
- [ ] `P1` GitHub Release 自动化
- [ ] `P1` SBOM
- [ ] `P1` 依赖漏洞扫描

---

# 17. 推荐 Sprint 顺序

## Sprint 1：基础抽象

- Backend Protocol
- HeadlessBackend
- Prompt File
- Cancel 修复
- FakeBackend
- 基线测试

交付：

- 现有 API 不变
- 执行链路完成解耦

## Sprint 2：Stateful Response

- SQLite
- 状态机
- Event Journal
- Orchestrator
- `/v1/responses`
- 查询、取消、SSE 重连

交付：

- 可创建、查询、取消和重连 Agent 任务

## Sprint 3：ACP Runtime

- ACP stdio
- Session
- Text/Tool/Plan/Usage
- Cancel
- Resume

交付：

- Grok 通过 ACP 执行，工具事件完整可见

## Sprint 4：权限闭环

- Policy Engine
- Permission Broker
- Approval API
- 审计日志
- Waiting 状态

交付：

- 文件修改、Shell 等可询问并继续执行

## Sprint 5：工作区隔离

- Worktree
- Lock
- Diff
- Cleanup

交付：

- 写任务默认不直接修改原工作区

## Sprint 6：MCP

- MCP Server
- consult/review/delegate
- status/cancel/diff
- Codex/Qoder/CodeBuddy 验证

交付：

- 其他 Agent 可将 Grok 作为外部 Agent 调用

## Sprint 7：安全与发布

- Scoped API Key
- Redaction
- Metrics
- E2E
- 文档
- Release

---

# 18. MVP 范围

首个可发布 MVP 建议只包含（对账：以下为 v0.2 代码已具备的 MVP 项）：

- [x] Backend 抽象
- [x] HeadlessBackend
- [x] SQLite
- [x] Response 状态机
- [x] `/v1/responses`
- [x] SSE 和事件重连
- [x] Tool Call 可见
- [x] Cancel
- [x] ACP stdio
- [x] Permission Broker
- [x] Approval API
- [x] `read_only` 和 `worktree`
- [x] `grok_consult`
- [x] `grok_review`
- [x] `grok_delegate`

MVP 暂不包含：

- [ ] 多用户
- [ ] PostgreSQL
- [ ] Redis
- [ ] 容器调度
- [ ] 管理 UI
- [ ] Remote ACP Serve
- [ ] 外部工具执行模式
- [ ] 复杂计费

---

# 19. 发布阻断条件

以下任一问题**仍成立**时，不应发布「正式版 / 生产硬安全门」；标记约定：

- `[x]` = 该阻断项已在代码中消除或充分缓解
- `[ ]` = 该问题仍可能成立，构成发布风险

- [ ] 权限请求可能被调用方绕过（默认 always_approve=False；Headless 仍强制；scoped key 有部分约束）
- [x] API Key 可突破 Workspace Allowlist（已强制 key/server allowlist 校验）
- [ ] 取消后存在残留进程（进程组终止已实现；正式孤儿扫描 / 启动恢复未完成）
- [x] 两个写任务可修改同一原工作区（in_place 排他写锁；默认禁止 in_place）
- [x] Permission Decision 非幂等（同决策幂等；冲突返回 409）
- [x] SSE 重连会丢事件（event journal + `Last-Event-ID` / `after_sequence`）
- [x] 原始 Thought 通过公共 API 暴露（默认 `include_thoughts=False`）
- [x] Prompt 暴露在进程列表（Headless 使用 `--prompt-file` + `0600`）
- [x] Key 明文存储（仅存 hash + pepper）
- [x] 服务默认监听公网（默认 `127.0.0.1`）
- [x] 服务默认 `always_approve`（默认 `False`；Headless 强制 approve 以保证 `grok -p` 可运行）
- [ ] 真实 Grok ACP E2E 未通过（有 opt-in 用例，未作为 CI 硬门）
- [ ] Codex/Qoder/CodeBuddy MCP 验证未完成

---

# 20. Definition of Done

单个任务完成必须满足：

1. 代码实现完成。
2. 单元测试完成。
3. 必要集成测试完成。
4. 类型检查通过。
5. Lint 通过。
6. API 或配置变更已写文档。
7. 安全影响已检查。
8. 错误处理已覆盖。
9. 日志中不泄露凭据。
10. 兼容性影响已记录。

整个方案完成必须满足：

1. HTTP 和 MCP 共用同一 Orchestrator。
2. ACP 是默认 Backend。
3. Headless 是兼容 Backend。
4. 权限询问可暂停和继续。
5. 任务可后台、查询、取消、重连。
6. 写任务默认 Worktree。
7. Token 权限可分离。
8. 工具、权限和状态有完整审计。
9. Codex、Qoder、CodeBuddy 可调用。
10. WorkBuddy 和 OpenAI SDK 仍可使用。
