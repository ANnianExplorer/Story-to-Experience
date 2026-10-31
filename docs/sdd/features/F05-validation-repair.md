# F05 SDD：分层检查、自动试玩与有限修复

> 设计基线；实现状态以 [登记表](../../feature-registry.json) 为准。
> 行为事实源：[本功能 SPEC](../../spec/features/F05-validation-repair.md)。相关决策：[ADR-0002](../../adr/0002-versioned-contracts.md)、[ADR-0003](../../adr/0003-evidence-and-content-review.md)、[ADR-0004](../../adr/0004-deterministic-shared-engine.md)、[ADR-0006](../../adr/0006-immutable-version-and-limited-patch.md)、[ADR-0007](../../adr/0007-isolated-dual-gate-delivery.md)。

## 目标与非目标

用可复查证据区分结构合法、逻辑可完成、真实界面可操作和内容待审；不判断自动趣味性或普遍教育效果。

## 分层与所有权

L2 ValidationService/RepairService；L3 TS validator+engine；L4 报告存储；L5 受限浏览器。依赖必须满足 [分层规则](../layers/README.md)，本功能不得成为跨层捷径。

## 主数据流

冻结候选 → Schema → 引用与语义 → 状态枚举 → 正常 UI 路径回放 → 报告；可修复错误生成允许补丁→新候选→全局复查。

## 数据与契约

validation_reports 包含 spec/source/runtime/asset/checker 哈希、搜索数量、路径/反例、截图和 trace；每轮修复保留父子关系。

公共 API、状态机和数据字段分别见 [API](../../spec/api.md)、[状态机](../../spec/state-machines.md)、[数据模型](../../spec/data-model.md)。

## 异常与竞争

上限为 inconclusive，不冒充无解；真正死路为 failed；引擎/解析器缺陷转开发；资料不足等待输入；超过两轮停止。

## 实施任务

| 任务 ID | 任务与边界 | 需求 | 依赖 |
|---|---|---|---|
| F05-T01 | **语义与状态校验器**：实现引用、DAG、完整排列、状态搜索和反向可完成性，报告未知。 | F05-R01,F05-R02 | F04-T01 |
| F05-T02 | **隔离真实浏览器**：从确定路径生成正常交互，保存关联哈希与 trace；执行器隔离。 | F05-R03 | F05-T01、F04-T02、F06-T01 |
| F05-T03 | **两轮补丁闭环**：分类错误、白名单补丁、全局复测、到限停止与问题转开发。 | F05-R04 | F05-T02、F07-T02、F06-T02 |

任务开始前补充本次允许路径与实际依赖版本；各任务按 [工作流](../../engineering/workflow.md) 交付真实证据，不能仅以文档完成结项。

## 回退与验收

任何失败候选不更新稳定版；模型不能修改检查器、删除必要目标或降低验收。

执行对应 SPEC 的全部适用 AT，报告正常、负向和竞争行为。未来测试放入相关模块的 tests 与端到端套件；登记实现位置后再升级状态。当前不提供不存在测试文件的虚假链接。

