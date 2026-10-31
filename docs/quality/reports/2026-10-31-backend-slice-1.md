# 后端切片 1 证据：领域骨架、项目用例、PostgreSQL 迁移

> 2026-10-31 · 范围：F01 部分实现（项目创建/读取/简报修订）、F02/F06/F07/F10/F11 领域对象与表结构。
> 结论：**切片内自动化测试通过；业务功能整体仍为 in_progress，不能宣称 F01 verified。**

## 变更

| 区域 | 内容 |
|---|---|
| `server/domain/` | 错误类型、文本规范化与码点半开区间、RFC 8785 子集规范 JSON、项目/简报、资料与事实、任务生命周期与预算、Agent 协议与计划、版本与补丁路径、对话会话与预算、交付与分享 |
| `server/application/` | 端口 Protocol、`ProjectService`（归属校验、简报修订冲突、游标分页） |
| `server/infrastructure/db/` | 21 张表的 SQLAlchemy 定义、仓储实现、Unit of Work、引擎构造 |
| `server/migrations/` | Alembic 基线迁移 `52f7f13bdfcb` |
| `apps/api/` | FastAPI 组合根、开发身份适配器（仅回环）、统一错误信封、项目 CRUD 路由 |
| `infra/compose.dev.yaml` | 本地 PostgreSQL 16，端口 127.0.0.1:55432 |

## 验证命令与实际结果

| 命令 | 环境 | 结果 |
|---|---|---|
| `cd server && ../.venv/Scripts/python.exe -m pytest` | Python 3.12.2，SQLite 内存库 | `37 passed` |
| `alembic upgrade head` → `downgrade base` → `upgrade head` | PostgreSQL 16（Docker，127.0.0.1:55432） | 三步均成功，21 张表建立 |
| `python scripts/check_docs.py` | 仓库根 | `passed`，503 链接，0 错误 |
| `python scripts/check_contracts.py` | 仓库根 | `passed`，0 错误（未改动 Schema） |
| `python scripts/check_ui.py` | 仓库根 | `passed`（未改动前端） |

测试覆盖的具体行为：

- 规范化幂等、NFC、码点切片、越界片段拒绝、段落切分；
- 规范 JSON 的 UTF-16 键排序、转义最短形式、浮点/非字符串键拒绝、固定 golden 哈希；
- 任务状态机终态不可倒退、租约接管使旧 token 失效、过期租约拒绝提交、取消后迟到写入被拒；
- 12 次调用共享预算、释放/结算边界、两轮修复上限、unknown 费用不可写零；
- Agent 工具矩阵越权拒绝、协议版本不匹配拒绝、跨项目交接拒绝、Review 不得批准、计划成环与缺链拒绝；
- 项目创建 owner 来自会话、跨用户统一 404、简报版本冲突保留历史、非法简报不落库；
- HTTP 层：健康检查、创建/读取、伪造 `owner_id` 无效、`expected_revision` 必填、409 冲突、未配置身份时 401。

## 未执行项与原因

| 项 | 状态 | 原因 |
|---|---|---|
| 真实 PostgreSQL 上的并发用例（F06-AT01/AT02 竞争、F07-AT02） | not_run | 竞态测试需独立数据库夹具与 `FOR UPDATE` 语义，SQLite 不支持，随下一个切片接入 |
| 真实模型调用 | not_run | 切片尚未接入 Provider 适配器；网关凭据已确认可用（见下） |
| 前端工作台 | not_run | 本切片不含 UI |
| 迁移在生产/CI 环境执行 | not_run | 仅本地 Docker 数据库验证 |

## 环境事实记录

- 模型网关 `ANTHROPIC_BASE_URL=https://api.modelverse.cn` 可用；`deepseek-v4.1-flash-1017` 与 `glm-5.3-flash` 均返回 200 与 usage。
- 默认模型名 `deepseek-v4.1-flash-1017[1M]`（带后缀）被网关拒绝（400 `param_error`），适配器必须使用不带后缀的 ID，且不得硬编码后缀。
- GitHub 远端 `git ls-remote` 在本机被连接重置（`SSL_read: Connection was reset`），推送步骤可能失败，届时如实报告。

## 剩余风险

1. 领域层尚未被真实并发写入检验；`active_for_project` 目前只做查询，唯一活动任务约束需数据库部分唯一索引补强。
2. 仓储 `EvidenceRepository.add_spans` 需要先 `prime_project()`，接口易误用，后续改为由应用层显式传入 project_id。
3. 开发身份适配器接受 `X-Actor-Id`，仅限回环地址；生产身份提供方未定，公开发布前必须替换。
4. 未知费用、租约时间全部依赖数据库时钟的实现仍待接入真实 PostgreSQL 用例验证。
