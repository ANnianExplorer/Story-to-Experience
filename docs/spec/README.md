# SPEC 行为与契约总目录

SPEC 定义“系统必须怎样表现”和可观察验收；实现方法在 SDD，选择理由在 ADR。Schema 只负责结构，跨引用、来源、执行与发布语义必须额外验证。

当前核心功能包括 [F10 多 Agent](features/F10-multi-agent.md) 和 [F11 双端 AI 对话](features/F11-ai-conversation.md)。ExperienceSpec 1.0 是确定性交互基座，完整在线体验另有版本化会话配置，不是首版排除对话。

| 核心文档 | 负责内容 |
|---|---|
| [功能规格目录](features/README.md) | 当前需求及验收；数量以登记表为准 |
| [前端视觉与动效](../frontend/README.md) | 主题、Token、组件、React 动画与可访问性 |
| [ExperienceSpec DSL](experience-spec.md) | 体验参与者动作、条件、效果、三机制和结构版本 |
| [API](api.md) | HTTP/SSE、幂等、权限和错误协议 |
| [数据模型](data-model.md) | 字段、不变量、索引、哈希、事务与迁移 |
| [状态机](state-machines.md) | 任务、阶段、质量、解析和版本指针 |
| [安全](security.md) | 上传、模型、沙盒、分享、隐私和删除 |
| [机器契约目录](../../packages/contracts/README.md) | Schema、正反样例和检查范围 |

需求编号 Fxx-Rxx、任务 Fxx-Txx、验收 Fxx-ATxx 不复用。原方案 A01—A20 映射在 [验收矩阵](../quality/acceptance.md)。非功能要求不能只写“安全、稳定、快速”，必须关联可执行检查和明确的未验证边界。

