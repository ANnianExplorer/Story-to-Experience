# 叙境 · Story-to-Experience

以多 Agent 协作和 AI 共创对话，把文化资料转成有出处的互动体验，并提供体验端 AI 导览与角色交流。

**当前阶段：两条最小业务链已贯通并在真实模型下验收（开发环境）。** 创作者链（上传→共创对话→多 Agent 计划/委派→带出处候选）与体验链（固定版本→AI 导览问答→引用）已可运行；自测 76+ 项、真实浏览器验收记录在 [浏览器验收报告](docs/quality/reports/2026-10-31-browser-acceptance.md)。生产部署、自动试玩、修订与打包仍未完成。

## 快速运行

只需要三条命令（在仓库根目录，Windows）：

```powershell
# 激活项目内的虚拟环境（可选；不激活就用 ./.venv/Scripts/python.exe 代替 python）
.\.venv\Scripts\Activate.ps1

python scripts/dev.py db            # 启动 PostgreSQL 并迁移到最新
python scripts/dev.py api           # 后端 http://127.0.0.1:8000
python scripts/dev.py web           # 工作台 :5173 与体验端 :5174
```

模型凭据从环境变量读取（`ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN`，可用 `XUJING_MODEL_*` 覆盖）；未配置时接口明确返回 `NOT_CONFIGURED`，不会自动退回模拟模式。`python scripts/dev.py all` 可一次启动数据库、API 与两个前端。

## 开发入口

先看 [V2：多 Agent 与 AI 对话架构](docs/architecture-and-design-v2.md)，确认方向、当前边界和开发顺序。上一版总览已标记被替代。

1. [CLAUDE.md：核心工程约束](CLAUDE.md)
2. [docs/README.md：文档总目录](docs/README.md)
3. [代码组织：按功能与分层](docs/sdd/code-structure.md)
4. [SDD 总架构](docs/sdd/architecture.md)
5. [实施路线](docs/roadmap.md)
6. [质量与证据](docs/quality/README.md)

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
