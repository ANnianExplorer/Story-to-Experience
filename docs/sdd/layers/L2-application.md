# L2 应用服务

> 范围：server/application 与 Worker 阶段调用。当前为待实现设计。

## 职责

用例包含创建项目、冻结证据、提交/恢复/取消任务、提交阶段、创建候选、申请审核、创建分享/导出。用例接受 authenticated actor 和资源 ID，先授权再执行业务。

## 数据流

入口解析 DTO → 用例验证领域不变量 → unit-of-work → repository/端口 → 持久事件；提交后执行外部副作用或由持久任务消费。

## 边界与禁止依赖

事务边界由应用管理，领域不提交事务；外部模型调用前登记预算/调用，结束后条件登记结果。不能在路由、LangGraph 或存储适配器各写一套晋级规则。

## 实施细节与检查

application 定义 Protocol/接口：ProjectRepository、RunRepository、VersionRepository、UnitOfWork、BlobStore、ModelProvider、ValidatorPort、PlaytestPort。测试用显式 fake，不自动替代缺失真实服务。

按 [分层目录](README.md) 核对上下游，功能落点见 [功能设计](../features/README.md)，真实门禁状态见 [质量目录](../../quality/gates.md)。

