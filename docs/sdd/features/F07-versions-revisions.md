# F07 SDD：不可变版本、局部修改与冲突

> 设计基线；实现状态以 [登记表](../../feature-registry.json) 为准。
> 行为事实源：[本功能 SPEC](../../spec/features/F07-versions-revisions.md)。相关决策：[ADR-0002](../../adr/0002-versioned-contracts.md)、[ADR-0003](../../adr/0003-evidence-and-content-review.md)、[ADR-0006](../../adr/0006-immutable-version-and-limited-patch.md)。

## 目标与非目标

任何修改可追溯，保留上一稳定体验；旧基准不静默覆盖，语义变化不复用旧审核。

## 分层与所有权

L1 差异/修改 UI；L2 VersionService/RevisionService；L3 Version/Patch/Impact；L4 版本仓储/文件。依赖必须满足 [分层规则](../layers/README.md)，本功能不得成为跨层捷径。

## 主数据流

指定 base_version → 事务校验 revision_head → 认领修订任务 → 影响分析 → 白名单补丁 → 新不可变候选 → 复测/重审 → 用户选择合格稳定版。

## 数据与契约

experience_versions、revision_requests、version_artifacts、项目 latest_candidate/revision_head/selected/stable 指针；源/规格/素材/运行时哈希。

公共 API、状态机和数据字段分别见 [API](../../spec/api.md)、[状态机](../../spec/state-machines.md)、[数据模型](../../spec/data-model.md)。

## 异常与竞争

过期基准 409；越权/未知路径补丁拒绝；验证失败仍保留候选和问题，但不改变 stable。

## 实施任务

| 任务 ID | 任务与边界 | 需求 | 依赖 |
|---|---|---|---|
| F07-T01 | **版本与哈希存储**：不可变版本体、父链、内容寻址与项目指针；报告作为追加记录。 | F07-R01,F07-R04 | F01-T01 |
| F07-T02 | **修订认领与补丁**：base CAS、活动任务约束、白名单 JSON Patch、受众修改影响。 | F07-R02,F07-R03 | F07-T01、F06-T01 |
| F07-T03 | **审核失效和回退**：影响 diff、证据传播、报告重绑、稳定晋级与安全回退。 | F07-R03,F07-R04 | F07-T02、F05-T01 |

任务开始前补充本次允许路径与实际依赖版本；各任务按 [工作流](../../engineering/workflow.md) 交付真实证据，不能仅以文档完成结项。

## 回退与验收

切回旧版只改指针并记录事件；旧版仍需当前授权/撤销检查，撤销来源许可后不能借回退恢复分享。

执行对应 SPEC 的全部适用 AT，报告正常、负向和竞争行为。未来测试放入相关模块的 tests 与端到端套件；登记实现位置后再升级状态。当前不提供不存在测试文件的虚假链接。

