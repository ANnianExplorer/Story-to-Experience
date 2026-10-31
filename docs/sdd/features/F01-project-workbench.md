# F01 SDD：项目、身份与创作者工作台

> 设计基线；实现状态以 [登记表](../../feature-registry.json) 为准。
> 行为事实源：[本功能 SPEC](../../spec/features/F01-project-workbench.md)。相关决策：[ADR-0001](../../adr/0001-modular-layered-architecture.md)、[ADR-0007](../../adr/0007-isolated-dual-gate-delivery.md)、[ADR-0008](../../adr/0008-evidence-driven-engineering.md)。

## 目标与非目标

让创作者管理自己的材料与体验，区分生成进度、技术质量和内容审核。首版不做组织管理与多人协作。

## 分层与所有权

前端视觉实现补充决策：[ADR-0009](../../adr/0009-frontend-visual-motion.md)；统一入口为 [前端规范](../../frontend/README.md)。共享主题不复制项目/任务状态。

L1 工作台/HTTP；L2 ProjectService；L3 Project/Brief；L4 项目仓储与身份适配器。依赖必须满足 [分层规则](../layers/README.md)，本功能不得成为跨层捷径。

## 主数据流

身份会话 → 创建项目/简报 → 工作台加载材料、任务、版本快照 → 订阅事件 → 展示私有预览；所有详情接口重新授权。

## 数据与契约

projects(owner_id, brief, revision_head_id, selected_version_id, stable_version_id)；工作台读模型按项目聚合，不复制权威状态。

公共 API、状态机和数据字段分别见 [API](../../spec/api.md)、[状态机](../../spec/state-machines.md)、[数据模型](../../spec/data-model.md)。

## 异常与竞争

身份过期提示重新登录；事件断档重新取快照；无来源/无版本显示可操作空态；409 保留用户输入并说明重新加载。

## 实施任务

| 任务 ID | 任务与边界 | 需求 | 依赖 |
|---|---|---|---|
| F01-T01 | **身份与项目骨架**：实现认证端口、所有者用例、项目 CRUD 和持久简报；仅开发身份时限制回环监听。 | F01-R01,F01-R02 | 无 |
| F01-T02 | **工作台主布局**：材料/来源、预览、任务/修改三栏和测试费用抽屉；空态、待审和 mock 标记。 | F01-R03 | F01-T01、F04-T02、F06-T01 |
| F01-T03 | **事件和失败交互**：SSE 续传、快照重载、取消和冲突输入保留。 | F01-R04 | F01-T02、F06-T03、F07-T02 |
| F01-T04 | **工作台设计系统落地**：共享 UI primitives/patterns、Token、响应式布局、来源抽屉与微交互；生产 React 类型/构建/键盘/减弱模式验证。 | F01-R05 | F01-T02；当前 Token 与静态预览不算本任务完成 |

任务开始前补充本次允许路径与实际依赖版本；各任务按 [工作流](../../engineering/workflow.md) 交付真实证据，不能仅以文档完成结项。

## 回退与验收

UI 可回退旧兼容客户端；简报修改保留修订记录；不能通过 UI 回退放宽后端权限。

执行对应 SPEC 的全部适用 AT，报告正常、负向和竞争行为。未来测试放入相关模块的 tests 与端到端套件；登记实现位置后再升级状态。当前不提供不存在测试文件的虚假链接。

