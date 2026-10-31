# F08 SDD：内容审核、分享、导出与撤销

> 设计基线；实现状态以 [登记表](../../feature-registry.json) 为准。
> 行为事实源：[本功能 SPEC](../../spec/features/F08-review-delivery.md)。相关决策：[ADR-0003](../../adr/0003-evidence-and-content-review.md)、[ADR-0006](../../adr/0006-immutable-version-and-limited-patch.md)、[ADR-0007](../../adr/0007-isolated-dual-gate-delivery.md)。

## 目标与非目标

让创作者清楚选择交付固定版本，有出处、有许可、审核可追溯；在线撤销完整但不承诺撤回下载副本。

## 分层与所有权

V2 补充：发布清单固定 DialogueProfile 与对话协议版本；在线分享可授权 Guide，会话额度单独控制。离线导出禁实时输入或明确引导到在线服务，不把固定问答冒充 AI。撤销资源和会话授权一并执行。

L1 审核/交付 UI；L2 DeliveryService；L3 Review/Share/ExportPolicy；L4 受保护存储与打包；L5 静态服务。依赖必须满足 [分层规则](../layers/README.md)，本功能不得成为跨层捷径。

## 主数据流

固定版本检查报告 → 人工逐项审核 → 事务复验双门槛/哈希/授权 → 受限投影 → 创建令牌分享或打包 → 逐资源访问 → 撤销。

## 数据与契约

content_reviews、review_items、shares(token_hash,version_id,expires_at,revoked_at)、exports(mode,manifest_hash)、artifacts 与许可证清单。

公共 API、状态机和数据字段分别见 [API](../../spec/api.md)、[状态机](../../spec/state-machines.md)、[数据模型](../../spec/data-model.md)。

## 异常与竞争

未审/失败/未知拒绝正式交付；到期/撤销/错误 token 所有资源失败；导出扫描发现私有全文/密钥中止。

## 实施任务

| 任务 ID | 任务与边界 | 需求 | 依赖 |
|---|---|---|---|
| F08-T01 | **审核对象与门槛**：覆盖范围、语义哈希、追加审核和资格查询，禁止模型批准。 | F08-R01,F08-R02 | F07-T01、F02-T02 |
| F08-T02 | **固定分享资源服务**：令牌哈希、到期/撤销、同一资源策略和无持久公共缓存。 | F08-R03 | F08-T01、F05-T02 |
| F08-T03 | **草稿/正式导出**：安全投影、manifest、许可证、断网验证、下载不可撤回说明。 | F08-R02,F08-R04 | F08-T01、F04-T03 |

任务开始前补充本次允许路径与实际依赖版本；各任务按 [工作流](../../engineering/workflow.md) 交付真实证据，不能仅以文档完成结项。

## 回退与验收

分享撤销是单向追加状态，不删除审核历史；下载包不可远程撤回；打包失败保留版本且不生成有效下载链接。

执行对应 SPEC 的全部适用 AT，报告正常、负向和竞争行为。未来测试放入相关模块的 tests 与端到端套件；登记实现位置后再升级状态。当前不提供不存在测试文件的虚假链接。

