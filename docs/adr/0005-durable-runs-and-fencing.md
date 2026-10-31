# ADR-0005：数据库租约与可恢复阶段

> 补充／局部替代：[ADR-0010](0010-multi-agent-and-conversation.md) 已将多 Agent 与双端 AI 对话纳入核心。确定性规则仍保留；在线对话的 Provider、预算、状态与在线/离线交付边界以新决策为准。

- 状态：Accepted（开发设计基线，实施待完成）
- 日期：2026-10-31
- 适用功能：F03,F05,F06,F07
- 检查：G06；实际状态见 [门禁表](../quality/gates.md)

## 背景

进程内队列无法跨重启保留任务，旧 Worker 迟到提交和重复投递会产生版本或费用错误。

## 决策

PostgreSQL 为任务真相，租约含递增 fencing token；阶段键绑定 run/input/stage_version，提交时核验 token、状态与租约。LangGraph 仅承载阶段编排和持久检查点，不能代替业务版本/预算/授权。

## 替代方案

内存队列不满足恢复；Redis/Celery 暂无必要；把 LangGraph checkpoint 当全局业务库会混淆事务与发布职责。

## 代价与约束

需实现事务、抢占、心跳、清理与竞争测试。对外调用只能尽量复用结果，网络未知窗口仍可能重复计费，不承诺全局 exactly-once。

## 复议条件

数据库调度出现可量化瓶颈再评估专用队列；迁移仍保留幂等和提交 fencing。

## 落地与验证

按 [总架构](../sdd/architecture.md)、[功能设计索引](../sdd/features/README.md) 和 [规格目录](../spec/README.md) 实施；需求/任务/验收由 [登记表](../feature-registry.json) 连接。门禁待建不算通过；发布须保存真实执行证据。

