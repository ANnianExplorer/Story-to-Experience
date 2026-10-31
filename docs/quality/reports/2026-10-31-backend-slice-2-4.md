# 后端切片 2-4 证据：多 Agent 生成链、双端对话与真实模型联调

> 2026-10-31 · 关联：F02/F03/F04/F06/F07/F08/F10/F11。
> 结论：**两条最小业务链已贯通并有真实模型调用证据**；产品仍未 released，
> 前端、自动试玩、浏览器门禁、生产身份与发布验收未完成。

## 变更概览

| 切片 | 标签 | 内容 |
|---|---|---|
| 1 | `v0.1.0-skeleton` | 领域对象、项目用例、PostgreSQL 迁移、API 骨架 |
| 2 | `v0.2.0-engine` | 共享确定性引擎、语义/状态校验器、契约派生类型、跨语言规范 JSON |
| 3 | `v0.3.0-creator-chain` | 资料上传与快照、多 Agent 编排、双端对话、交付门槛（脚本化模型） |
| 4 | `v0.4.0-http-api` | 完整 HTTP 路由、真实网关适配、结构化生成加固、真实联调 |

## 实际验证

| 检查 | 环境 | 结果 |
|---|---|---|
| `pytest -c server/pytest.ini server/tests apps/api/tests` | Python 3.12.2 / SQLite 内存库 | **62 passed, 2 skipped** |
| 同一套件，`XUJING_TEST_DATABASE_URL=…xujing_test` | PostgreSQL 16（Docker） | 46 passed（切片 2 时点） |
| `alembic upgrade head` → `downgrade base` → `upgrade head` | PostgreSQL 16 | 三步成功，21 张表 |
| `node --test packages/engine/tests/*.test.ts` | Node 24 | 16 passed |
| `node --test packages/validator/tests/*.test.ts` | Node 24 | 10 passed |
| `node scripts/generate.mjs --check` | Node 24 | 生成类型未过期 |
| `python scripts/check_docs.py` | 仓库根 | passed（0 错误） |
| `python scripts/check_contracts.py` | 仓库根 | passed |
| `python scripts/check_ui.py` | 仓库根 | passed |
| **真实模型端到端生成** | `XUJING_LIVE_MODEL=1`，网关 `api.modelverse.cn`，`deepseek-v4.1-flash-1017` | **succeeded**，validation=passed |
| **真实模型 Guide 对话** | 同上 | 一轮带引用回答 + 一轮注入拒绝 |

### 真实模型调用记录（最后一次成功运行）

| 角色 | 输入 token | 输出 token | 费用状态 |
|---|---:|---:|---|
| coordinator | 55 | 1475 | unknown |
| evidence | 759 | 839 | unknown |
| experience_designer | 1407 | 4500 | unknown |
| experience_builder | 154 | 2748 | unknown |
| review | 2367 | 4108 | unknown |

共 5 次调用，与 F10 的“规划、证据、设计、构建、审校”五项基础调用一致；
费用状态为 `unknown`，因为网关未提供可核对单价，未写入任何金额。

## 真实联调中暴露并修复的问题

| 问题 | 现象 | 修复 |
|---|---|---|
| 网关模型名后缀 | `deepseek-v4.1-flash-1017[1M]` 被网关拒绝（400） | 适配器使用不带后缀的模型 ID，后缀由环境变量决定 |
| 隐藏推理占用输出预算 | Builder 在 8000 token 上限仍返回空文本 | 请求 `thinking.type=disabled`（结构化产物场景） |
| 模型不知道嵌套 Schema | 条件写成 `{"all": ["F_tool_found"]}`、顶层字段自造 | 提示词注入由 Schema 生成的紧凑结构骨架 + 一个**经 Schema 校验的最小示例** + 条件规则 |
| 模型接线错误 | completion/flag/跳转绑定错乱 | 结构由服务端按蓝图生成，模型只写面向参与者的文字 |
| 租约过期导致自身提交失败 | 长时间生成 `STALE_FENCING_TOKEN` | 增加租约心跳续期；最终提交仍校验 token 与过期时间 |
| 完成页被标为 supported 但无事实 | Schema 校验失败 | 完成页固定为 `adaptation` |
| 事件序号重复 | 同一事务内多次 append 唯一键冲突 | 序号改为数据库原子自增返回 |
| 预算计数丢失 | 重新加载 run 覆盖内存账本 | 提交时合并内存账本 |

## 未执行项与原因

| 项 | 状态 | 原因 |
|---|---|---|
| 前端工作台 / 体验运行端 React | not_run | 尚未开始；`apps/design-preview` 仅为视觉参考 |
| Playwright 自动试玩（F05-T02） | not_run | 执行器未实现；校验器仅产出可回放动作路径 |
| 移动端/真实手机、键盘与减弱动效验收 | not_run | 无 UI |
| 并发竞争用例（F06-AT01/02、F07-AT02 真库竞争） | not_run | 目前只有状态机层单测；真库 `FOR UPDATE` 竞争测试待补 |
| 分享 / 导出端到端（含撤销后资源读取） | not_run | 路由与门槛已实现，未做浏览器级验证 |
| 生产身份、部署、备份恢复 | not_run | 开发身份仅限回环地址 |
| 对话长会话压缩、断线重连事件补发 | not_run | 当前为同步执行路径，流式事件在生产路径待接入 |
| 真实模型的对话质量评估（引用准确性人工核对） | not_run | 只验证了结构与引用范围，未做内容质量评分 |

## 剩余风险

1. 真实模型输出仍可能触达预算上限；当前以有界重试 + 显式失败处理，尚无跨模型的质量基线。
2. `_complete_json` 的第二次尝试会放宽 token 上限至 8000，需在 F06 预算中显式计入（已计入调用次数，未单独计墙钟）。
3. 对话的流式为同步执行后按块回放，真正的 provider 流式与断线续传未接入生产路径。
4. 结构化生成把接线交给服务端，模型只写文案：这保证了可玩性，但若蓝图本身与证据不符，问题会前移到 Designer/Review；需在用户试用中检验。
5. GitHub 推送在本机间歇性失败（`SSL_read: Connection was reset`），远端最新状态以实际推送结果为准。
