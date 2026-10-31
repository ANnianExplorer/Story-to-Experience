# 体验契约核心目录

- [机器 Schema](experience-spec.schema.json)：ExperienceSpec v1.0.0，Draft 2020-12。
- [完整人工样例](examples/workshop.valid.json)：四场景、三机制、三个必要任务；全部内容为合成教学设定。
- [样例出处投影](examples/workshop.evidence.json)：仅演示公开引文，非生产来源快照格式。
- [反例变更集](examples/invalid-cases.json)：八种结构/语义失败，基于正例逐项替换。
- [文字与执行语义](../../docs/spec/experience-spec.md)：结构之外的不变量。
- [契约检查脚本](../../scripts/check_contracts.py)：Schema 自检、正反例、有限的语义一致性与排序独立预期。

运行 `python scripts/check_contracts.py`，需安装根 requirements-docs.txt。该 Python 脚本是仓库契约样例检查器，**不是生产玩家引擎或完整状态验证器**。它不执行任务、不证明所有可达状态、不做历史事实认证；生产行为仍由未来 TS 引擎和校验器实现。

首个 TS 应用提交增加由 Schema 生成类型的工具链和 golden fixtures，首个 API 提交增加 OpenAPI 快照及生成客户端。当前没有派生类型，不手写镜像。

