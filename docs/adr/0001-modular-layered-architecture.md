# ADR-0001：模块化单体与跨语言分层

> 补充／局部替代：[ADR-0010](0010-multi-agent-and-conversation.md) 已将多 Agent 与双端 AI 对话纳入核心。确定性规则仍保留；在线对话的 Provider、预算、状态与在线/离线交付边界以新决策为准。

- 状态：Accepted（开发设计基线，实施待完成）
- 日期：2026-10-31
- 适用功能：F01,F02,F03,F04,F05,F06,F07,F08,F09
- 检查：G02；实际状态见 [门禁表](../quality/gates.md)

## 背景

首版团队小，既需要 Python 的资料/模型生态，又需要浏览器与校验器共享 TS 状态语义。若先拆微服务，事务和交付成本会超过收益。

## 决策

采用单仓库、模块化应用：React 工作台/体验运行端、FastAPI API、持久 Worker、独立试玩执行器和 PostgreSQL。Python 按 domain/application/infrastructure 分层，TS 按 contracts/engine/validator/UI 分层。仅 API/Worker 组合根组装依赖。

## 替代方案

纯 TS 全栈可减少语言切换，但与既有 Python 方案差异大；微服务利于独立扩容但增加分布式一致性；自由生成独立项目会扩大依赖与执行风险。

## 代价与约束

需维护 TS/Python 边界协议和两套工具链。只有共享引擎定义体验参与者逻辑；Python 通过受限 JSON 调用，不重写规则。

## 复议条件

出现明确独立扩容、团队自治或隔离部署需求时复议，先用测量证明模块化单体不足。

## 落地与验证

按 [总架构](../sdd/architecture.md)、[功能设计索引](../sdd/features/README.md) 和 [规格目录](../spec/README.md) 实施；需求/任务/验收由 [登记表](../feature-registry.json) 连接。门禁待建不算通过；发布须保存真实执行证据。

