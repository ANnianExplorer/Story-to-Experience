# 功能设计核心目录

每功能独立维护分层落点、数据流、失败恢复与三个实施任务。行为预期在对应 SPEC，不在 SDD 复制第二套。当前均待实现，状态见 [登记表](../../feature-registry.json)。

当前核心补充：[F10 多 Agent 规划与协作](F10-multi-agent.md)、[F11 双端 AI 对话](F11-ai-conversation.md)。二者属于首版主链路，详见 [V2 总览](../../architecture-and-design-v2.md)。

| 功能 | SDD | SPEC | 跨层位置 |
|---|---|---|---|
| F01 | [项目、身份与创作者工作台](F01-project-workbench.md) | [SPEC](../../spec/features/F01-project-workbench.md) | L1 工作台/HTTP；L2 ProjectService；L3 Project/Brief；L4 项目仓储与身份适配器 |
| F02 | [材料、事实与证据快照](F02-sources-evidence.md) | [SPEC](../../spec/features/F02-sources-evidence.md) | L1 上传与来源卡；L2 EvidenceService；L3 SourceSpan/Claim/Snapshot；L4 解析、仓储、文件 |
| F03 | [知识转译、蓝图与真实生成](F03-blueprint-generation.md) | [SPEC](../../spec/features/F03-blueprint-generation.md) | L1 蓝图与缺口界面；L2 DesignService/GenerationService；L3 Objective/Blueprint；L4 Provider 与证据检索 |
| F04 | [ExperienceSpec、共享引擎与体验运行端](F04-runtime-player.md) | [SPEC](../../spec/features/F04-runtime-player.md) | L1 React 体验运行端；L3 TS contracts/engine；L5 静态运行时；无 Python 体验参与者规则副本 |
| F05 | [分层检查、自动试玩与有限修复](F05-validation-repair.md) | [SPEC](../../spec/features/F05-validation-repair.md) | L2 ValidationService/RepairService；L3 TS validator+engine；L4 报告存储；L5 受限浏览器 |
| F06 | [持久任务、恢复、事件与费用](F06-runs-budget.md) | [SPEC](../../spec/features/F06-runs-budget.md) | L1 Run HTTP/SSE；L2 RunService/预算；L3 生命周期；L4 PostgreSQL/checkpoint/Provider；Worker 组合根 |
| F07 | [不可变版本、局部修改与冲突](F07-versions-revisions.md) | [SPEC](../../spec/features/F07-versions-revisions.md) | L1 差异/修改 UI；L2 VersionService/RevisionService；L3 Version/Patch/Impact；L4 版本仓储/文件 |
| F08 | [内容审核、分享、导出与撤销](F08-review-delivery.md) | [SPEC](../../spec/features/F08-review-delivery.md) | L1 审核/交付 UI；L2 DeliveryService；L3 Review/Share/ExportPolicy；L4 受保护存储与打包；L5 静态服务 |
| F09 | [安全、部署、恢复与评估](F09-operations-security.md) | [SPEC](../../spec/features/F09-operations-security.md) | 跨层授权/日志；L4 迁移备份；L5 Compose/隔离/发布；质量门禁 |

