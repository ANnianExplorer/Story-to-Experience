# 叙境 · Story-to-Experience

以多 Agent 协作和 AI 共创对话，把文化资料转成有出处的互动体验，并提供体验端 AI 导览与角色交流。

**当前阶段：开发基线已建立，业务应用待实现。** 仓库包含规范、设计、契约、样例和检查脚本；API、Worker、体验运行端及真实模型生成链路尚未实现。

## 开发入口

先看 [V2：多 Agent 与 AI 对话架构](docs/architecture-and-design-v2.md)，确认方向、当前边界和开发顺序。上一版总览已标记被替代。

1. [CLAUDE.md：核心工程约束](CLAUDE.md)
2. [docs/README.md：文档总目录](docs/README.md)
3. [SDD 总架构](docs/sdd/architecture.md)
4. [实施路线](docs/roadmap.md)
5. [质量与证据](docs/quality/README.md)
6. [前端视觉与 React 动效规范](docs/frontend/README.md)

## 已可执行的检查

需要 Python 3.12 或更新兼容版本，在仓库根目录执行：

```powershell
python scripts/check_docs.py
python -m pip install -r requirements-docs.txt
python scripts/check_contracts.py
python scripts/check_ui.py
```

文档检查仅用标准库；契约检查使用 jsonschema。CI 定义见 [.github/workflows/governance.yml](.github/workflows/governance.yml)，尚不能据此宣称远端 CI 或产品验收已通过。应用启动命令在对应应用落地后增加。

产品范围与原方案改进见 [产品基线](docs/product.md) 及 [依据记录](docs/basis-and-changes.md)。
