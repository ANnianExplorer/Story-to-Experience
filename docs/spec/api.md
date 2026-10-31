# HTTP、SSE 与工具契约

> 开发设计契约，尚无运行中的 API/OpenAPI。首个 API 提交必须输出 OpenAPI 和生成客户端，再接工作台。基础前缀 /api/v1，JSON 使用 snake_case，时间为带 Z 的 UTC ISO 8601，业务 ID 使用 UUID。ExperienceSpec 内部节点使用短稳定 ID。

## 公共协议

认证使用可替换服务端会话/身份端口；生产提供方待定。任何非分享路由均需认证和项目所有权。不存在与不属于当前用户的资源统一 404。分享资源只使用令牌访问冻结投影，不获得项目 API 权限。

成功响应返回 data、request_id；列表附 next_cursor。错误统一：
```json
{"error":{"code":"VERSION_CONFLICT","message":"基准版本已变化，请重新加载。","object_id":"version-id","retryable":false,"details":{}},"request_id":"request-id"}
```
details 不回显密钥、绝对路径、SQL 或私有全文。401 身份缺失，404 不存在/无权，409 并发/幂等冲突，413 体积超限，415 类型不支持，422 字段/规则错误，429 限流，503 依赖暂不可用。等待补资料用任务 waiting_input，不能反复 500。

## 资源接口

| 方法/路径 | 请求关键字段 | 响应及语义 |
|---|---|---|
| POST /projects | name,brief | 201；owner 来自会话 |
| GET /projects | cursor,limit≤50 | 200；只列自己的 |
| GET/PATCH /projects/{project_id} | PATCH: brief,expected_revision | 200；冲突 409，修改不覆盖历史简报 |
| POST /projects/{project_id}/sources | multipart file 或 text；license_note | 202，source_id/parse_run_id；先验额再解析 |
| GET /sources/{source_id} | 无 | 200，归属与解析状态，不暴露文件路径 |
| GET /sources/{source_id}/spans | cursor | 200，稳定片段与定位 |
| GET /projects/{project_id}/claims | content_type,cursor | 200，事实与证据 |
| POST /projects/{project_id}/source-snapshots | source_ids,claim_revisions | 201，新不可变快照 |
| POST /projects/{project_id}/runs | source_snapshot_id,brief_revision,auto_continue | 202，run_id；要求 Idempotency-Key |
| GET /runs/{run_id} | 无 | 200，lifecycle/stage/quality/usage/last_sequence |
| GET /runs/{run_id}/events | Last-Event-ID 或 after | 200 text/event-stream，持久补发 |
| POST /runs/{run_id}/resume | expected_wait_revision,source_snapshot_id,blueprint_id | 202；只有 waiting_input 可继续；新输入重新冻结 |
| POST /runs/{run_id}/cancel | 无 | 200 当前终态或已取消快照，幂等 |
| GET /projects/{project_id}/blueprints | cursor | 200，目标/任务/依据/缺口 |
| POST /blueprints/{blueprint_id}/confirm | expected_hash | 200；冻结选择，不能改写原文 |
| POST /projects/{project_id}/revisions | base_version_id,instruction | 202；要求 Idempotency-Key；预留修改槽 |
| GET /versions/{version_id} | 无 | 200，规格与哈希、质量投影 |
| GET /versions/{version_id}/diff | against_version_id | 200；同项目才能比较 |
| GET /versions/{version_id}/reports | cursor | 200；报告和受控证据地址 |
| PATCH /projects/{project_id}/selection | selected_version_id | 200，仅私有预览指针 |
| POST /projects/{project_id}/stable | version_id,expected_stable_version_id | 200；CAS 和双门槛 |
| POST /versions/{version_id}/reviews | semantic_hash,items,decision,notes | 201；审核人为会话身份 |
| POST /versions/{version_id}/exports | mode=draft/formal | 202，export_id；正式双门槛 |
| GET /exports/{export_id} | 无 | 200 状态/受保护下载 |
| POST /versions/{version_id}/shares | expires_at,license_ack | 201；首次返回随机 token，数据库仅保存哈希 |
| DELETE /shares/{share_id} | 无 | 204；幂等撤销 |
| GET /share/{token}/manifest | 无 | 200 固定版本投影；无效/撤销 404 |
| GET /share/{token}/resources/{resource_id} | 无 | 200；同一令牌逐资源校验 |

这是 endpoint 最小设计，身份登录回调等协议待生产身份方案确定后单独扩展。PATCH 项目与选择使用服务器修订号；ExperienceSpec 不通过普通 PATCH 原地修改。

## 幂等与并发

Idempotency-Key 为客户端随机 UUID，作用域 actor+method+route+project。服务器保存请求规范摘要、run_id 和响应。相同键相同摘要返回原 202；相同键不同摘要为 409 IDEMPOTENCY_CONFLICT。首版保存至少项目生命周期，不能键过期后无提示重新调用模型。

不同键也受项目活动任务唯一约束，409 ACTIVE_RUN 并返回当前 run_id（仅所有者）。版本基准先检查 revision_head，再认领活动修改槽；409 不静默覆盖。

## SSE

事件有 id=递增 sequence，event=stage/usage/quality/input_required/terminal，data 含 run_id、type、payload、created_at。不传原文、密钥和模型原始输出。心跳无 id，不计序号。

按最后已应用序号补发，客户端按 id 去重。若事件已归档或序号非法，订阅前返回 409 EVENT_CURSOR_EXPIRED 并指示重新获取任务快照；客户端取快照 last_sequence 后重连。快照和最后序号从同一事务一致性视图读取，不能丢中间事件。保留策略首版至少覆盖活动任务与终态 30 天；归档后仍能读取最终快照。

## 内部工具

所有工具服务端再次核验 project/run/token/权限。工具只允许资源 ID、有限查询和冻结哈希，无自由 SQL、shell、任意 URL/path。

| 工具 | 输入 → 输出 | 限制 |
|---|---|---|
| retrieve_evidence | snapshot_id,span_ids/query → spans | 同项目且冻结快照 |
| get_mechanic_catalog | runtime_version → schema+limits | 仅实现机制 |
| validate_spec | candidate_id,spec_hash → report | 超限明确 unknown |
| check_reachability | candidate_id,limits → path/counterexample/status | 共用 TS 引擎 |
| render_preview | version_id → 临时预览句柄 | 不返回自由可替换 URL |
| run_playtest | preview_handle,path_ids → report/trace | 仅受控目标、无密钥 |
| apply_patch | base_hash,patch → 新候选/影响 | 白名单与父关系 |
| export_bundle | version_id,mode → artifact | 模型不能越过正式交付门槛 |

内部执行器协议为 JSON 请求/响应，含 protocol_version、request_id、input_hash、resource_ids、limits；输出含 status、errors、evidence_keys。命令参数由服务固定，JSON 经标准输入或受控文件传递，不拼接 shell。

## V2：多 Agent 与 AI 对话接口

以下均位于 /api/v1，尚未实现。创建/发消息重新核验身份、项目、版本与预算，客户端传入的 agent/role 名称不构成授权。

| 接口 | 请求／返回与权限 |
|---|---|
| GET /runs/{run_id}/agent-tasks | 项目所有者读取计划、子任务、产物、交接和费用；不返回内部推理 |
| POST /projects/{project_id}/conversations | kind=creator、base_version_id、brief_revision；返回 conversation_id |
| POST /conversations/{conversation_id}/turns | client_turn_id、message、context_version；202 返回 turn_id，重复同键同摘要复用，不同摘要 409 |
| GET /conversation-turns/{turn_id}/events | 按序补发 text_delta/citation/tool_status/action_proposed/error/completed；仅公开投影 |
| POST /conversation-turns/{turn_id}/cancel | 幂等取消，禁止新调用/迟到完整提交，部分文本明确标未完成 |
| POST /share/{token}/sessions | 校验分享后签发仅该固定版本的 experience_session，不授予项目管理权限 |
| POST /experience-sessions/{session_id}/conversations | 仅 kind=guide，绑定已发布 DialogueProfile/版本与公开证据，不能选择任意 Agent 或 Provider |

同会话一个活动 turn；不同体验参与者使用独立会话和额度，不受项目唯一生成 run 锁串行化。429 表示限流/配额，409 CONTEXT_CHANGED 要求确认新上下文或新会话。重连以 turn 快照/序号恢复；最终文本及引用持久化，部分输出不是最终答案。

AgentTaskEnvelope/AgentResult、DialogueProfile、ConversationBinding 为版本化伴随协议；DialogueProfile 至少含 id、profile_version、persona/adaptation_note、source_scope、objective_ids、hint_policy、allowed_actions、model_policy_ref。发布清单固定 profile_hash 与 conversation_protocol_version，旧 ExperienceSpec 1.0 不静默加未知字段。

