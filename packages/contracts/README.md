# 体验契约核心目录

- [机器 Schema](experience-spec.schema.json)：ExperienceSpec v1.0.0，Draft 2020-12。
- [Agent 协议 Schema](agent-protocol.schema.json)：F10 委派信封、结果、计划。
- [对话配置 Schema](dialogue-profile.schema.json)：F11 DialogueProfile 与 turn 输出。
- [派生 TypeScript 类型](generated/)：由 Schema 生成，**不手改**。
- [完整人工样例](examples/workshop.valid.json)：四场景、三机制、三个必要任务；全部内容为合成教学设定。
- [样例出处投影](examples/workshop.evidence.json)：仅演示公开引文，非生产来源快照格式。
- [反例变更集](examples/invalid-cases.json)：八种结构/语义失败，基于正例逐项替换。
- [文字与执行语义](../../docs/spec/experience-spec.md)：结构之外的不变量。
- [契约检查脚本](../../scripts/check_contracts.py)：Schema 自检、正反例、有限的语义一致性与排序独立预期。

## 派生类型

```powershell
cd packages/contracts
npm ci
npm run generate   # 写入 generated/*.ts
npm run check      # CI：生成结果过期则失败
```

生成器（[scripts/generate.mjs](scripts/generate.mjs)）只做机械派生：导出名来自根 Schema 的 `title`，`maxItems > 4` 的数组折叠为 `T[]` 以免类型爆炸，但**运行时约束仍以 JSON Schema 为准**。共享引擎（`packages/engine`）与校验器（`packages/validator`）引用这些类型，不手写第二份公共结构。

## 检查边界

`python scripts/check_contracts.py` 是仓库契约样例检查器，**不是生产玩家引擎或完整状态验证器**。生产行为由 `packages/engine`（纯函数引擎）与 `packages/validator`（语义检查 + 状态搜索）实现，两者各有独立测试：

```powershell
cd packages/engine    && npm ci && npm run check && npm test
cd packages/validator && npm ci && npm run check && npm test
```

当前没有 OpenAPI 快照与生成客户端；首个 API 契约稳定后补齐。
