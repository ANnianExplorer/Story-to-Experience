# F04 SDD：ExperienceSpec、共享引擎与体验运行端

> 设计基线；实现状态以 [登记表](../../feature-registry.json) 为准。
> 行为事实源：[本功能 SPEC](../../spec/features/F04-runtime-player.md)。相关决策：[ADR-0002](../../adr/0002-versioned-contracts.md)、[ADR-0004](../../adr/0004-deterministic-shared-engine.md)。

## 目标与非目标

无需模型与数据库即可播放合法手工规格，三类机制共享明确动作语义，确定性互动可独立运行；在线体验通过 F11 提供真实 AI 导览与角色对话。

## 分层与所有权

前端视觉实现补充决策：[ADR-0009](../../adr/0009-frontend-visual-motion.md)；按 [动效规范](../../frontend/motion.md) 从 Token 生成 Motion preset，动画不反向控制引擎。

L1 React 体验运行端；L3 TS contracts/engine；L5 静态运行时；无 Python 体验参与者规则副本。依赖必须满足 [分层规则](../layers/README.md)，本功能不得成为跨层捷径。

## 主数据流

加载固定 runtime+Schema → 结构/语义校验 → 初始状态 → 体验参与者动作 → 引擎原子执行 → 新状态/反馈 → 复盘/重玩。

## 数据与契约

ExperienceSpec、PlayerState(scene_id,flags)、ActionInput、ActionResult；本地会话序号用于展示恢复，不影响任务规则。

公共 API、状态机和数据字段分别见 [API](../../spec/api.md)、[状态机](../../spec/state-machines.md)、[数据模型](../../spec/data-model.md)。

## 异常与竞争

未知运行时拒绝播放；非法动作/坏排序返回错误且状态不变；错误答案给依据和重试；加载损坏清单不执行。

## 实施任务

| 任务 ID | 任务与边界 | 需求 | 依赖 |
|---|---|---|---|
| F04-T01 | **纯函数引擎**：实现 initialState/evaluateCondition/applyAction 及输入拒绝，独立手工预期。 | F04-R01,F04-R02 | 无 |
| F04-T02 | **三个组件和来源复盘**：React 读取引擎输出，提供提示、来源、非拖拽排序、完成/重玩。 | F04-R03,F04-R04 | F04-T01 |
| F04-T03 | **兼容与静态运行**：运行时清单、哈希验证、离线加载与跨版本拒绝。 | F04-R01,F04-R04 | F04-T02 |
| F04-T04 | **体验参与者端视觉与动效**：短标题分组、场景转场、线索反馈、排序布局；减少动效、焦点与卸载清理；生产 React 构建及交互回归。 | F04-R05 | F04-T02；当前样式预览仅为设计样本 |

任务开始前补充本次允许路径与实际依赖版本；各任务按 [工作流](../../engineering/workflow.md) 交付真实证据，不能仅以文档完成结项。

## 回退与验收

固定版本绑定兼容体验运行端；新运行时不覆盖旧包；重玩只清空本地会话，不影响创作者数据。

执行对应 SPEC 的全部适用 AT，报告正常、负向和竞争行为。未来测试放入相关模块的 tests 与端到端套件；登记实现位置后再升级状态。当前不提供不存在测试文件的虚假链接。

