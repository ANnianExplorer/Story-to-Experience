# ADR-0002：结构契约单一事实源

- 状态：Accepted（开发设计基线，实施待完成）
- 日期：2026-10-31
- 适用功能：F02,F03,F04,F05,F07
- 检查：G01,G03；实际状态见 [门禁表](../quality/gates.md)

## 背景

HTTP DTO、模型结构化输出和体验运行端配置若各写一份类型，容易在 Python/TS 间漂移；字段合法也不能证明可运行。

## 决策

ExperienceSpec 以 packages/contracts 下 Draft 2020-12 JSON Schema 为结构权威，TS 类型由其生成，Python 使用同一 Schema 校验。HTTP 用 FastAPI/Pydantic 生成 OpenAPI 与 TS 客户端。语义约束、来源和状态检查按 SPEC 单独执行。

## 替代方案

只用 Pydantic 派生所有对象会将运行时 DSL 绑定 API 框架；只用 TS 类型无法校验不可信 JSON；双向手工镜像最容易漂移。

## 代价与约束

引入生成步骤和兼容性检查；生成文件不可手工编辑。schema_version 与 runtime_version 分开；升级先验证消费者再发布。

## 复议条件

新字段无法向后兼容、需要新机制或发现生成链无法可靠表达联合类型时，以新 ADR/Schema 版本处理。

## 落地与验证

按 [总架构](../sdd/architecture.md)、[功能设计索引](../sdd/features/README.md) 和 [规格目录](../spec/README.md) 实施；需求/任务/验收由 [登记表](../feature-registry.json) 连接。门禁待建不算通过；发布须保存真实执行证据。

