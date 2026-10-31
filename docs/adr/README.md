# ADR 决策总目录

> 更新：2026-10-31。Accepted 表示本次采用的开发设计基线，不表示业务已实现、已验证或已获领域审核。

ADR 记录难逆转、跨模块或高风险选择。每份必须有背景、决策、替代、代价、复议条件和验证。Proposed → Accepted → Superseded/Deprecated；替代保留旧文并指向新编号，编号不复用。

| 编号 | 决策 | 功能 | 验证 |
|---|---|---|---|
| ADR-0001 | [模块化单体与跨语言分层](0001-modular-layered-architecture.md) | F01,F02,F03,F04,F05,F06,F07,F08,F09 | G02 |
| ADR-0002 | [结构契约单一事实源](0002-versioned-contracts.md) | F02,F03,F04,F05,F07 | G01,G03 |
| ADR-0003 | [证据快照与独立内容审核](0003-evidence-and-content-review.md) | F02,F03,F05,F07,F08 | G04,G07 |
| ADR-0004 | [受限 DSL 与共享确定性引擎](0004-deterministic-shared-engine.md) | F03,F04,F05 | G03,G05 |
| ADR-0005 | [数据库租约与可恢复阶段](0005-durable-runs-and-fencing.md) | F03,F05,F06,F07 | G06 |
| ADR-0006 | [不可变版本与受限补丁](0006-immutable-version-and-limited-patch.md) | F05,F07,F08 | G04,G06 |
| ADR-0007 | [隔离执行与双门槛交付](0007-isolated-dual-gate-delivery.md) | F01,F05,F08,F09 | G07,G08 |
| ADR-0008 | [规格驱动、可执行门禁和证据状态](0008-evidence-driven-engineering.md) | F01,F02,F03,F04,F05,F06,F07,F08,F09 | G01,G08 |
| ADR-0009 | [参考驱动的视觉系统与 React 动效](0009-frontend-visual-motion.md) | F01,F04；约束其余前端 | G01,G02,G05,G08 |
| ADR-0010 | [多 Agent 与双端 AI 对话进入核心范围](0010-multi-agent-and-conversation.md) | F03,F04,F06,F08,F09,F10,F11；撤销旧范围收缩 | G01,G06,G07,G08 |

[返回总目录](../README.md)。新增决策使用 [ADR 模板](../engineering/templates/adr.md)。

