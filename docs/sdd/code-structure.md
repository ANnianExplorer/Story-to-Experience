# 代码组织：按功能与分层

> 后端（Python）与前端（TypeScript）都遵循「先按功能，再按层」的目录划分。
> 本文件说明目录职责与依赖方向，新增文件前先对照本表；具体不变量取 [CLAUDE.md](../../CLAUDE.md) 与 [分层设计](../sdd/layers/README.md)。

## 后端 `server/`

```text
server/
├─ domain/                      纯领域对象与不变量（无框架、无 I/O、无模型 SDK）
│  ├─ shared/                  跨功能原语
│  │  ├─ errors.py             稳定错误码与 DomainError 家族
│  │  ├─ ids.py                UUID 生成/校验
│  │  ├─ text.py               规范化、码点切片、段落切分
│  │  └─ canonical_json.py     RFC 8785 子集规范序列化与哈希
│  ├─ projects.py              项目与简报
│  ├─ evidence.py              资料、片段、事实、快照
│  ├─ runs.py                  生命周期、阶段、预算账本、模型调用
│  ├─ versions.py              版本不可变性、修订基线与补丁白名单
│  ├─ agents.py                Agent 角色、工具矩阵、信封/结果/计划
│  ├─ conversations.py         会话、turn、对话配置、引用、配额
│  └─ delivery.py              审核、分享令牌、导出模式
├─ application/                 用例与端口（不依赖 FastAPI/SQLAlchemy/Provider SDK）
│  ├─ ports.py                 仓储、UnitOfWork、BlobStore、ModelProvider、Validator
│  ├─ projects.py / evidence.py / runs.py / delivery.py   每功能一个服务
│  ├─ generation/              多 Agent 生成链（F03/F10）
│  │  ├─ roles.py              角色提示词、输出 Schema、JSON 提取
│  │  ├─ orchestration.py      DAG 执行、审校∥校验、修复、预算
│  │  ├─ builder.py            确定性结构装配（模型只写文案）
│  │  ├─ spec_validation.py    ExperienceSpec/DialogueProfile Schema 校验
│  │  └─ spec_skeleton.py      由 Schema 生成的结构骨架（提示词用）
│  └─ conversations/           双端对话（F11）
│     ├─ service.py            会话、turn 执行、引用映射、注入拒绝
│     └─ retrieval.py          词汇检索（按允许作用域）
└─ infrastructure/              端口实现（可引用领域与驱动）
   ├─ db/                      tables.py / repositories.py / uow.py / engine.py
   ├─ llm/gateway.py           Anthropic 兼容网关适配器 + 显式 MockProvider
   ├─ parsing/documents.py     隔离解析（文本与文本 PDF）
   ├─ storage/blobs.py         内容寻址本地存储
   └─ validation/node_validator.py  TS 校验器的受限 JSON 桥
```

依赖方向固定为 `apps → application → domain`，`infrastructure` 实现 `application` 的端口，在组合根注入。领域层不得 import 应用层或基础设施。

## API `apps/api/`

```text
apps/api/xujing_api/
├─ main.py            组合根：选实现、装中间件、挂路由
├─ asgi.py            uvicorn 入口
├─ config/settings.py 环境变量与本地/生产校验
├─ core/              identity.py（开发身份）、errors.py（信封与错误映射）
├─ deps.py            FastAPI 依赖：把 app.state 里的适配器注入路由
├─ schemas/requests.py 请求模型（Pydantic）
└─ routers/           每个功能一个路由模块
   ├─ meta.py projects.py runs.py delivery.py conversations.py
```

路由只做三件事：鉴权、DTO ↔ 用例、错误映射。业务规则不得写在路由里。

## 前端 `apps/workbench/`

```text
apps/workbench/src/
├─ main.tsx           入口：挂载与路由切换
├─ styles.css         只消费 packages/ui/tokens.css 的派生变量
├─ lib/               与 React 无关的逻辑（可单测）
│  ├─ api.ts          HTTP 客户端、错误类型、响应类型
│  ├─ workbench-state.ts  状态机、阶段标签、门禁、预算显示
│  └─ router.ts       hash 路由解析
├─ hooks/use-workbench.ts  客户端与 reducer 的 React 绑定
├─ components/        面板与外壳（只接收 scope，不自行请求）
│  ├─ app-shell.tsx primitives.tsx
│  ├─ material-panel.tsx run-panel.tsx chat-panel.tsx version-panel.tsx
└─ pages/             页面组合
   ├─ project-list.tsx project-workbench.tsx
```

- `lib/` 下的文件必须能在 Node 里直接单测（不 import React/DOM）。
- `components/` 不发请求；请求通过 `scope.run()` 触发，错误统一落到状态机。
- 颜色、间距、动效数值只来自 `packages/ui/tokens.json` 派生的 CSS 变量。

## 共享包 `packages/`

| 包 | 职责 | 依赖 |
|---|---|---|
| `contracts/` | 版本化 JSON Schema 与派生 TS 类型 | 无 |
| `engine/` | 确定性体验引擎（纯函数） | contracts 类型 |
| `validator/` | 语义检查 + 状态搜索；stdin/stdout JSON 桥 | engine |
| `ui/` | Token 权威源与派生 CSS | 无 |

## 检查入口

```powershell
python scripts/check_docs.py          # 文档链接、编号、登记表一致性
python scripts/check_contracts.py     # Schema 正反例
python scripts/check_ui.py            # Token 与派生 CSS
python -m pytest -c server/pytest.ini server/tests apps/api/tests
cd packages/engine && npm test
cd packages/validator && npm test
cd apps/workbench && npm run check && npm test && npm run build
```
