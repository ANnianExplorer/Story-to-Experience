# F06 SDD：持久任务、恢复、事件与费用

> 设计基线；实现状态以 [登记表](../../feature-registry.json) 为准。
> 行为事实源：[本功能 SPEC](../../spec/features/F06-runs-budget.md)。相关决策：[ADR-0001](../../adr/0001-modular-layered-architecture.md)、[ADR-0005](../../adr/0005-durable-runs-and-fencing.md)、[ADR-0006](../../adr/0006-immutable-version-and-limited-patch.md)。

## 目标与非目标

让生成可取消、可恢复、有限成本，重复投递不会重复提交业务版本；不承诺外部模型恰好执行一次。

## 分层与所有权

L1 Run HTTP/SSE；L2 RunService/预算；L3 生命周期；L4 PostgreSQL/checkpoint/Provider；Worker 组合根。依赖必须满足 [分层规则](../layers/README.md)，本功能不得成为跨层捷径。

## 主数据流

幂等提交 → 唯一活动任务 → Worker 租约/token → 预留预算并登记调用 → 阶段执行 → 条件提交 → 事件/检查点 → 下一阶段或等待/终态。

## 数据与契约

runs、run_steps、run_events、model_calls、budget_reservations、idempotency_requests；事件以 run 内递增 sequence 持久化。

公共 API、状态机和数据字段分别见 [API](../../spec/api.md)、[状态机](../../spec/state-machines.md)、[数据模型](../../spec/data-model.md)。

## 异常与竞争

Worker 失联后租约过期再抢占，旧 token 拒绝；超时未知用量标 unknown；等待输入释放租约但保留活动占位。

## 实施任务

| 任务 ID | 任务与边界 | 需求 | 依赖 |
|---|---|---|---|
| F06-T01 | **任务表与抢占**：生命周期、唯一活动约束、幂等记录、租约/token、阶段提交和持久事件。 | F06-R01,F06-R02 | F01-T01 |
| F06-T02 | **Provider 预算与记录**：调用前预留、实际结算、unknown 窗口、两轮/12 次/墙钟上限。 | F06-R04 | F06-T01 |
| F06-T03 | **恢复、取消与重连**：检查点复用、输入新快照恢复、取消竞争与事件断档。 | F06-R02,F06-R03 | F06-T01、F06-T02 |

任务开始前补充本次允许路径与实际依赖版本；各任务按 [工作流](../../engineering/workflow.md) 交付真实证据，不能仅以文档完成结项。

## 回退与验收

取消不逆转终态；失败保留原版本；重试新 attempt 不能清空累计调用/修复/费用计数。

执行对应 SPEC 的全部适用 AT，报告正常、负向和竞争行为。未来测试放入相关模块的 tests 与端到端套件；登记实现位置后再升级状态。当前不提供不存在测试文件的虚假链接。

