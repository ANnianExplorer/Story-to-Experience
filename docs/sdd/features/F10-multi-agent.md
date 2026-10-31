# F10 SDD：多 Agent 任务图与交接

行为见 [SPEC](../../spec/features/F10-multi-agent.md)。状态以 [登记表](../../feature-registry.json) 为准。

## 分层与数据流

L1 工作台展示对话、计划和执行轨迹；L2 AgentOrchestrationService 做调度、授权和提交；L3 Plan/AgentTask/Handoff/Artifact 定义不变量；L4 LangGraph、Provider、仓储与工具适配。Agent 不是新的部署层。

Coordinator 收集制作意图 → Evidence 提取与检索 → Designer 形成目标/场景/对话设计 → Builder 产出 ExperienceSpec 与 DialogueProfile → Review 与 Validator/Playtest 分支汇合 → Repair 有限修订 → 人工审核与交付。

Guide Agent 的在线会话复用 AgentProfile/工具授权，但不进入长任务的每轮生成 DAG。任务之间只交接 brief/snapshot/blueprint/version/report 等结构引用，按 project/version/run/token 验证。

## 消息与所有权

AgentTaskEnvelope 包含 protocol_version、agent_id、task_id、parent_task_id、project_id、run_id、input_refs、input_hash、profile_version、allowed_tools、budget_ref、fencing_token。AgentResult 包含 status、artifact_refs、citation_refs、issues、usage_ref、handoff_to、reason_code。参数不是授权，服务端再次校验。

新增 agent_tasks、agent_artifacts、agent_handoffs、agent_reviews；全局 run 与预算沿用 F06。产物先冻结，Coordinator 经应用服务有条件提交；Review 不直接修改版本。

## 实施任务

| 任务 ID | 内容 | 需求 | 依赖 |
|---|---|---|---|
| F10-T01 | 计划/子任务/交接协议、AgentProfile、七角色权限矩阵与追踪 | F10-R01,F10-R02 | F02/F06 最小骨架 |
| F10-T02 | 依赖图执行、并行审校汇合、输入快照与共享预算 | F10-R01,F10-R03,F10-R04 | F10-T01 |
| F10-T03 | 恢复/取消/幂等竞争、真实轨迹 UI 和评估 | F10-R02,F10-R03,F10-R04 | F10-T02、F05 检查器 |

回退以保留旧候选和记录失败为准，不能静默降级到单 Agent 后继续宣称多 Agent 已运行。若启用显式单 Agent 对照模式，必须独立标记与统计。

