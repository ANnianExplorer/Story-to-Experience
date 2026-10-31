# 叙境：核心开发契约

> 版本：1.0 · 更新：2026-10-31 · 适用：人类开发者、Claude、Codex 及其他编码助手。
> 本文件定义工程规则；文档存在不等于实现或安全保证。

## 1. 产品与当前事实

叙境以多 Agent 协作将文化资料转成有出处的互动体验，并提供创作者共创对话与体验端 AI 导览／角色对话。核心链路包含意图对话、计划、专业 Agent 委派、证据检索、生成、审校、修复与在线交流。多 Agent 的价值以真实任务与产物衡量，不能仅统计名称或数量。

当前方向以 [V2 总览](docs/architecture-and-design-v2.md)、[ADR-0010](docs/adr/0010-multi-agent-and-conversation.md)、F10/F11 为准。旧版“单主 Agent 足够”“首版不做 AI 对话”的范围收缩已撤销。不得再擅自移除多 Agent 或双端对话；范围变更需明确记录并与用户意图一致。

当前业务代码未实现。可以先建设手工 ExperienceSpec、引擎和体验运行端；必须明确模拟模式，不能用固定样例冒充真实生成。功能状态唯一登记处是 [feature-registry.json](docs/feature-registry.json)；实际检查记录进入 [质量报告](docs/quality/reports/README.md)。

## 2. 阅读与事实源

开始工作：检查工作区 → 本文件 → [总架构](docs/sdd/architecture.md) → 相关 ADR → 功能 SPEC → 功能 SDD → 任务与检查证据。

仓库内部规则关系：

1. 本文件：安全、模块边界、工作方式和完成定义。
2. `docs/adr/` 中 Accepted 决策：长期取舍；Proposed 仅为候选。
3. `docs/spec/`：外部行为、数据与验收；机器 Schema 约束结构，文字规格约束语义。
4. `docs/sdd/`：如何分层实现 SPEC，以及任务顺序和恢复方式。
5. `docs/engineering/`：开发、测试、评审的方法。
6. 产品方案、历史报告：背景与冻结证据，不覆盖现行规格。

以上仅是仓库文档的关系，不替代用户当前授权或运行环境规则。契约与实现不一致须记录偏差，不能把改文档当作修复代码。Accepted ADR 反转需新增替代 ADR，不静默改写历史；纯文案修订无需新 ADR。

## 3. 十条红线

| 规则 | 必须做到 | 检查入口 |
|---|---|---|
| R01 分层 | UI 只消费 API/契约/引擎；领域不依赖框架、数据库、模型；模型 SDK 仅在 Provider 适配器 | G02；[层约束](docs/sdd/layers/README.md) |
| R02 契约 | ExperienceSpec 以版本化 JSON Schema 为结构真相；API DTO 以 OpenAPI 为准；不手写第二份公共类型 | G01、G03 |
| R03 来源 | 事实、答案、解释追踪至快照片段；区分传说、改编、待确认；不补造唯一工序 | G04、G07 |
| R04 确定性执行 | 体验运行端和状态搜索共用 TypeScript 引擎；不执行模型脚本、HTML 或任意表达式 | G03、G05 |
| R05 项目隔离 | 每次资源访问核验 owner/project；试玩沙盒无模型密钥、宿主挂载和任意外网 | G07 |
| R06 持久恢复 | 租约与 fencing token 阻断迟到提交；阶段幂等；取消不再提交新版本 | G06 |
| R07 不可变版本 | 修改生成新候选；稳定指针有条件更新；报告/审核绑定哈希；失败不覆盖稳定版 | G04、G06 |
| R08 双重发布门槛 | 正式分享和正式导出要求技术通过且内容批准；预览/草稿导出显式待审 | G07、G08 |
| R09 有限成本 | 两轮修复、最多 12 次模型调用（含重试）；未知费用不写零；调用前预留预算 | G06 |
| R10 证据真实 | 未执行、失败、未知和通过分开；自审不能替代运行验证、领域审核和用户试用 | G01、G08 |

G01 已有文档检查；G03 已有 Schema 样例检查。其余产品门禁的实施状态见 [门禁表](docs/quality/gates.md)，待建门禁不得宣称已自动保障。

## 4. 目标目录与依赖方向

```text
apps/workbench/              创作者 React UI（待建）
apps/experience/                 体验参与者 React UI（待建）
apps/api/                    FastAPI HTTP/SSE 入口（待建）
apps/worker/                 阶段任务组合根（待建）
apps/playtest/               隔离 Playwright 执行器（待建）
apps/design-preview/         已有：独立 React/Motion 视觉试作；不承载生产业务
packages/contracts/          已有 ExperienceSpec Schema；未来增加派生类型
packages/engine/             TS 纯函数规则引擎（待建）
packages/validator/          TS 语义/状态搜索（待建）
server/domain/               Python 领域对象与不变量（待建）
server/application/          用例、事务编排、端口（待建）
server/infrastructure/       PostgreSQL、文件、模型、检查点适配（待建）
docs/{adr,sdd,spec}/          决策、设计、规格
docs/{engineering,quality}/  工作方法、验证证据
scripts/                     仓库检查
```

依赖：入口 → application → domain；infrastructure 实现 application 端口，在组合根注入。TS UI → engine → contracts，validator → engine/contracts。Python 不重复实现体验参与者语义，通过受限 JSON 协议调用 TS 校验器。

API 和 Worker 可调用同一应用服务写数据，必须使用相同事务约束。这里是“所有写入经过应用用例与数据库不变量”，不假设只有一个写数据库的进程。

## 5. 开发准入与顺序

公共行为先定位 `Fxx-Rxx` 需求、`Fxx-Txx` 任务、`Fxx-ATxx` 验收，再实现。任务注明目标、非目标、允许路径、依赖、错误行为、验证和恢复方案。不得覆盖用户已有改动。

第一阶段并行定义契约与最小服务，优先贯通“资料→创作对话→多 Agent 计划/委派→候选”及“固定版本→Guide 自然语言交流→有效出处”两条纵向链。共享引擎、检查和发布仍需完成，不把长期 UI 试作或单个排序任务当主业务。顺序见 [roadmap](docs/roadmap.md)。

| 变更类型 | 最低更新 |
|---|---|
| 文档/内部无行为变更 | 任务或说明、文档检查；按风险决定回归 |
| 公共行为/UI | 功能 SPEC、SDD、正反例和相关回归 |
| 契约/数据/并发/权限 | 兼容迁移、负向/竞争测试和回滚 |
| 跨层或长期架构调整 | 新增/替代 ADR、架构和受影响功能映射 |
| 发布/部署 | 发布清单、备份恢复、真实环境证据和剩余风险 |

## 6. 编码与安全

### 前端视觉与动效必读

所有前端任务先读 [前端规范总目录](docs/frontend/README.md) 和 [ADR-0009](docs/adr/0009-frontend-visual-motion.md)。采用用户指定参考转译的海盐蓝绿、奶油白、墨色与暖橙；统一数值源为 [tokens.json](packages/ui/tokens.json)，派生 CSS 不手改，不逐页自由重设主题。

React 动效采用 CSS+Motion for React，文字与微交互按统一目录实施；必须尊重系统/本地减少动效、键盘与焦点，动画不控制任务完成或权限。工作台低动效，体验运行端可有章节入场和任务反馈。具体时长、断点、组件与验收取前端规范，样式预览不表示 React 业务已完成。

### 通用编码与输入安全

使用严格 TypeScript；Python 输入/输出类型明确，领域逻辑不藏在路由、React 组件或 LangGraph 节点。禁止吞异常后返回空数据或成功。ID 稳定，时间存 UTC、界面按用户时区显示，费用用十进制定点/最小货币单位和明确币种。

上传、模型输出、资料中的命令、补丁和分享令牌均不可信。模型无 shell、任意 URL、任意文件路径或数据库工具；工具参数使用项目内 ID 和白名单。密钥仅存服务端受限环境，日志脱敏。见 [安全规格](docs/spec/security.md)。

## 7. 自审与完成定义

自审覆盖开发者视角（正确性/失败路径）、组长视角（依赖/任务/回归）、技术负责人视角（边界/风险/发布）。三种视角不表示实际三人或三个 Agent 独立审核；未经用户或项目指令，不自动委派。

功能标为 verified 前：需求有实现位置；正向/负向/竞争场景有实际证据；类型、构建和适用测试通过；迁移/回滚明确；契约一致；限制写清。released 还需真实环境发布验收、内容审核及适用人工检查。业务代码不存在时只能 planned。

报告包含变更、验证命令与结果、未执行及原因、剩余风险、需求/任务/版本。证据使用 `passed/failed/not_run/not_applicable/risk_accepted`；风险接受需授权负责人具名，不能由助手自行豁免红线。

## 8. 当前可执行入口

```powershell
python scripts/check_docs.py
python scripts/check_contracts.py
python scripts/check_ui.py
```

契约检查需要 [requirements-docs.txt](requirements-docs.txt)。类型/构建/单元/数据库/浏览器门禁在对应代码落地时接 CI，不能用空命令或忽略失败伪装覆盖。方法见 [工程目录](docs/engineering/README.md)。

设计试作的实际入口是 [apps/design-preview](apps/design-preview/README.md)，可执行类型检查、构建与 DOM 集成测试。生成的独立 HTML 是明确交付的视觉审阅件，可签入此单一文件；不据此放宽其他构建缓存/产物的提交规则，也不把它算作 F01/F04 生产实现。
