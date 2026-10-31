# 分层架构核心目录

| 层 | 独立文档 | 允许依赖 | 禁止 |
|---|---|---|---|
| L1 展示与接入 | [L1](L1-presentation.md) | API客户端、契约、纯引擎；路由调用 application | UI 接数据库/模型；路由藏业务规则 |
| L2 应用用例 | [L2](L2-application.md) | domain、端口、事务抽象 | 直接依赖 React/Provider SDK/存储驱动 |
| L3 领域与引擎 | [L3](L3-domain-engine.md) | 标准库、领域值对象、契约 | 框架、I/O、网络、系统时间和数据库 |
| L4 基础设施 | [L4](L4-infrastructure.md) | 实现 L2 端口，可引用领域与驱动 | 绕过用例发布版本、跨项目裸读写 |
| L5 执行与交付 | [L5](L5-execution-delivery.md) | 受限协议、冻结清单、报告 | 模型控制终端/宿主、任意出口 |

L5 是部署信任边界，不是允许反向依赖的业务层。入口 apps/api、apps/worker 是依赖组装根，可引用 L2 和 L4；业务代码不能借组合根作为捷径。边界检查尚待源码落地，不能用空目录扫描结果证明 G02 通过。

