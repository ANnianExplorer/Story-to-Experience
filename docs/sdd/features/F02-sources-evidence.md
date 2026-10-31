# F02 SDD：材料、事实与证据快照

> 设计基线；实现状态以 [登记表](../../feature-registry.json) 为准。
> 行为事实源：[本功能 SPEC](../../spec/features/F02-sources-evidence.md)。相关决策：[ADR-0002](../../adr/0002-versioned-contracts.md)、[ADR-0003](../../adr/0003-evidence-and-content-review.md)、[ADR-0007](../../adr/0007-isolated-dual-gate-delivery.md)。

## 目标与非目标

上传授权资料并提供稳定可核对的证据，保留传说和改编性质，不用网页抓取或 OCR 补全资料。

## 分层与所有权

L1 上传与来源卡；L2 EvidenceService；L3 SourceSpan/Claim/Snapshot；L4 解析、仓储、文件。依赖必须满足 [分层规则](../layers/README.md)，本功能不得成为跨层捷径。

## 主数据流

校验文件 → 隔离解析 → 规范化文本/页段定位 → 保存快照与片段 → 事实提取 → 事实—片段关联 → 人工校正产生新快照。

## 数据与契约

source_documents、source_spans、claims、claim_evidence、source_snapshots；快照成员保存内容哈希和解析版本；原文与公开引文分开。

公共 API、状态机和数据字段分别见 [API](../../spec/api.md)、[状态机](../../spec/state-machines.md)、[数据模型](../../spec/data-model.md)。

## 异常与竞争

扫描 PDF 为 NO_EXTRACTABLE_TEXT，不是成功空白；超额/类型错误返回明确错误；冲突事实保持待确认；解析超时不覆盖旧快照。

## 实施任务

| 任务 ID | 任务与边界 | 需求 | 依赖 |
|---|---|---|---|
| F02-T01 | **上传与隔离解析**：实现输入限额、签名检查、纯文本规范化、隔离解析和空文本错误。 | F02-R01,F02-R02 | F01-T01 |
| F02-T02 | **快照和事实关系**：建片段/事实/快照/证据关系，保存性质、限定语和不可变定位。 | F02-R02,F02-R03 | F02-T01 |
| F02-T03 | **来源卡和影响追踪**：原文定位、修正产生新快照、反向依赖查询和审核失效。 | F02-R04 | F02-T02、F07-T01 |

任务开始前补充本次允许路径与实际依赖版本；各任务按 [工作流](../../engineering/workflow.md) 交付真实证据，不能仅以文档完成结项。

## 回退与验收

旧快照不可变；修正和删除产生新快照，既有版本继续绑定旧证据但可撤销其分享资格；隐私删除依专门流程处理。

执行对应 SPEC 的全部适用 AT，报告正常、负向和竞争行为。未来测试放入相关模块的 tests 与端到端套件；登记实现位置后再升级状态。当前不提供不存在测试文件的虚假链接。

