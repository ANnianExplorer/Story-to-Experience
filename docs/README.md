# 叙境开发文档总目录

> 更新：2026-10-31 · 基线 v1.0 · 应用待实现。

核心入口是 [CLAUDE.md](../CLAUDE.md)。**ADR 解释为何选择；SDD 说明怎样实现和拆任务；SPEC 定义必须满足的行为、契约和验收。** 同一规则只维护一个权威正文，其余链接引用。

**当前方向入口：[V2：多 Agent 协作与 AI 对话架构](architecture-and-design-v2.md)。** 已按用户纠正撤销单主 Agent／无 AI 对话的范围收缩；[V1](architecture-and-design.md) 仅保留历史。

## 文档与约束文件树

```text
CLAUDE.md                         核心红线、工作契约、完成定义
AGENTS.md                         其他编码工具的薄入口
docs/
  README.md                       总导航
  product.md                      产品范围和限额
  basis-and-changes.md             依据、参考与方案改进
  roadmap.md / status.md           开发顺序与全局状态
  feature-registry.json           功能 ID、依赖和唯一功能状态
  adr/README.md + 0001～0010       决策与替代方案
  frontend/README.md              视觉、组件、React 动效与样式预览
  sdd/README.md + architecture.md  总体实现架构
    layers/README.md + L1～L5      每层职责、边界和数据流
    features/README.md + F01～F11  含多 Agent 与双端对话的功能设计
  spec/README.md                  行为与契约总入口
    experience-spec.md            体验 DSL 和动作语义
    api.md / data-model.md        接口和数据不变量
    state-machines.md / security.md
    features/README.md + F01～F11  每功能需求与验收
  engineering/README.md           开发、编码、文档和自审
    templates/                    ADR、功能、任务与证据模板
  quality/README.md               门禁、验收、发布与报告
    reports/README.md             冻结检查证据索引
packages/contracts/               机器 Schema、合成正反例
scripts/                          文档与契约检查
.github/                          CI 定义和 PR 模板
```

## 总目录

| 区域 | 核心入口 | 用途 |
|---|---|---|
| 产品 | [产品基线](product.md)、[依据与调整](basis-and-changes.md) | 定位、范围、输入资料与改进 |
| ADR | [决策目录](adr/README.md) | 当前决策、替代方案、代价和复议条件 |
| SDD | [设计目录](sdd/README.md)、[总架构](sdd/architecture.md) | 分层、进程、数据流和功能设计 |
| SPEC | [规格目录](spec/README.md) | 需求、验收、API、数据、DSL、状态与安全 |
| 前端 | [视觉与动效总目录](frontend/README.md) | 指定参考、Token、组件、React 动画与验收 |
| 工程 | [工程目录](engineering/README.md) | 工作流、编码、变更和三视角自审 |
| 质量 | [质量目录](quality/README.md) | 门禁、20 项验收映射、证据和发布 |
| 计划 | [实施路线](roadmap.md)、[当前状态](status.md) | 切片、依赖、待决事项和真实进度 |
| 登记 | [功能登记表](feature-registry.json) | 需求/任务/验收 ID、文档和唯一功能状态 |

## 功能导航

| ID | 功能 | 设计 | 规格 |
|---|---|---|---|
| F01 | 项目、身份与工作台 | [SDD](sdd/features/F01-project-workbench.md) | [SPEC](spec/features/F01-project-workbench.md) |
| F02 | 材料、事实与证据 | [SDD](sdd/features/F02-sources-evidence.md) | [SPEC](spec/features/F02-sources-evidence.md) |
| F03 | 知识转译与生成 | [SDD](sdd/features/F03-blueprint-generation.md) | [SPEC](spec/features/F03-blueprint-generation.md) |
| F04 | 规格引擎与体验运行端 | [SDD](sdd/features/F04-runtime-player.md) | [SPEC](spec/features/F04-runtime-player.md) |
| F05 | 检查、试玩与有限修复 | [SDD](sdd/features/F05-validation-repair.md) | [SPEC](spec/features/F05-validation-repair.md) |
| F06 | 持久任务、恢复与费用 | [SDD](sdd/features/F06-runs-budget.md) | [SPEC](spec/features/F06-runs-budget.md) |
| F07 | 版本、局部修改与冲突 | [SDD](sdd/features/F07-versions-revisions.md) | [SPEC](spec/features/F07-versions-revisions.md) |
| F08 | 内容审核、分享与导出 | [SDD](sdd/features/F08-review-delivery.md) | [SPEC](spec/features/F08-review-delivery.md) |
| F09 | 安全、运维与评估 | [SDD](sdd/features/F09-operations-security.md) | [SPEC](spec/features/F09-operations-security.md) |
| F10 | 多 Agent 规划与协作 | [SDD](sdd/features/F10-multi-agent.md) | [SPEC](spec/features/F10-multi-agent.md) |
| F11 | 创作 AI 对话／体验 AI 导览与角色对话 | [SDD](sdd/features/F11-ai-conversation.md) | [SPEC](spec/features/F11-ai-conversation.md) |

## 推荐阅读

开发者：核心规则 → 架构 → 功能 SPEC → 功能 SDD → 契约 → 验收。负责人：产品 → ADR → 架构 → 路线 → 门禁和状态。首次上手先看 F04/F05，再读 F02/F03/F06，多 Agent 与 AI 对话按 F10/F11 核心路线实施，部署复杂度按实测需要增加。
