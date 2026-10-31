# F03 SDD：知识转译、蓝图与真实生成

> 设计基线；实现状态以 [登记表](../../feature-registry.json) 为准。
> 行为事实源：[本功能 SPEC](../../spec/features/F03-blueprint-generation.md)。相关决策：[ADR-0001](../../adr/0001-modular-layered-architecture.md)、[ADR-0002](../../adr/0002-versioned-contracts.md)、[ADR-0003](../../adr/0003-evidence-and-content-review.md)、[ADR-0004](../../adr/0004-deterministic-shared-engine.md)、[ADR-0005](../../adr/0005-durable-runs-and-fencing.md)。

## 目标与非目标

把文化关系转为体验参与者任务，生成固定组件可执行的规格。由 F10 的专业 Agent 协作完成，并支持 F11 的创作对话与体验对话。

## 分层与所有权

L1 蓝图与缺口界面；L2 DesignService/GenerationService；L3 Objective/Blueprint；L4 Provider 与证据检索。依赖必须满足 [分层规则](../layers/README.md)，本功能不得成为跨层捷径。

## 主数据流

冻结简报与证据 → 提取事实和缺口 → 选择教学目标 → 查机制目录 → 生成蓝图 → 确认或显式自动草稿 → 生成规格 → 提交 F05 检查。

## 数据与契约

blueprints 及 task_bindings；记录 model/provider/prompt_version、输入摘要、raw_output 引用、调用 ID、结构修复次数。

公共 API、状态机和数据字段分别见 [API](../../spec/api.md)、[状态机](../../spec/state-machines.md)、[数据模型](../../spec/data-model.md)。

## 异常与竞争

依据不足 waiting_input；不支持机制提示缩减；模型格式错误有界重试；供应商不可用失败且保留调用记录；不回退为伪真实 mock。

## 实施任务

| 任务 ID | 任务与边界 | 需求 | 依赖 |
|---|---|---|---|
| F03-T01 | **证据到蓝图**：实现受限检索、目标映射和机制目录，保留缺口与理由。 | F03-R01,F03-R02 | F02-T02、F04-T01 |
| F03-T02 | **Provider 与结构化生成**：统一适配器、真实调用记录、Schema 校验；外部调用遵循预算。 | F03-R03 | F03-T01、F06-T02 |
| F03-T03 | **确认/等待与闭环**：蓝图确认、自动草稿和补资料恢复接入编排与验证。 | F03-R04 | F03-T02、F05-T01、F06-T03 |

任务开始前补充本次允许路径与实际依赖版本；各任务按 [工作流](../../engineering/workflow.md) 交付真实证据，不能仅以文档完成结项。

## 回退与验收

生成失败保留已有稳定版；提示词和模型配置版本化，新版本不修改历史输入或输出。

执行对应 SPEC 的全部适用 AT，报告正常、负向和竞争行为。未来测试放入相关模块的 tests 与端到端套件；登记实现位置后再升级状态。当前不提供不存在测试文件的虚假链接。

