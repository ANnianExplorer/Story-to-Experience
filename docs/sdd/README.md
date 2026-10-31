# SDD 系统与软件设计总目录

SDD 描述怎样实现 SPEC，并以任务串起开发；不重复维护需求原文。所有设计目前是开发基线，业务实现状态以 [登记表](../feature-registry.json) 为准。

当前总览：[V2 多 Agent 与 AI 对话](../architecture-and-design-v2.md)。核心新增 [F10 协作](features/F10-multi-agent.md) 与 [F11 双端对话](features/F11-ai-conversation.md)，旧串行无对话收缩已撤销。

| 核心文档 | 内容 |
|---|---|
| [总架构](architecture.md) | 模块、进程、依赖、主数据流与事务边界 |
| [分层目录](layers/README.md) | 五层独立设计及禁用依赖 |
| [前端设计系统](../frontend/README.md) | 视觉数值、组件边界、响应式和 React 动效 |
| [功能目录](features/README.md) | 功能逐层落点、流程、任务和回退 |
| [SPEC 总目录](../spec/README.md) | 行为、接口、状态、验收依据 |
| [ADR 总目录](../adr/README.md) | 当前设计的理由和替代方案 |
| [工作流](../engineering/workflow.md) | 规格驱动的准入、实施、自审和证据 |

设计变更先检查受影响的契约、状态、数据迁移、调用方、审核、权限和回归；架构选择反转用新 ADR，不在功能文档里偷偷绕过。

