# F11 SDD：双端对话服务与 RAG

行为见 [SPEC](../../spec/features/F11-ai-conversation.md)，长期决策见 [ADR-0010](../../adr/0010-multi-agent-and-conversation.md)。生产实现 planned。

## 架构

L1 创作者对话区、体验端“问导览/与角色交谈”；L2 ConversationService、ContextBuilder、TurnExecutor 与动作授权；L3 Session/Turn/DialogueProfile/Citation/Quota；L4 Provider、RAG、会话仓储和流式事件。

生成由 Worker 执行；低延迟对话由 API 的异步会话用例调用同一服务端 Provider 端口，不排在数分钟生成任务之后。可按负载独立扩容 API/在线对话副本，首版无需每 Agent 独立微服务。

## 上下文与权限

创作者上下文：会话目标、项目权限、简报修订、来源快照、当前版本、约束摘要、近期消息与检索证据。Guide 上下文：固定发布版本、角色设定/改编标记、场景/线索只读摘要、允许公开的证据投影、提示级别与近期消息。Guide 不读取私有整份原文。

系统约束/事实锚点与会话摘要分开；摘要不创造新事实。回答输出 text、citations、suggested_actions、answerability。引用由服务端映射到有效片段；导航/提示动作经白名单校验，对话不能直接改领域状态。

## 存储与接口

新增 conversation_sessions、conversation_turns、conversation_messages、conversation_citations、context_snapshots。turn 有 client_turn_id 幂等键、固定版本/hash、status、sequence、provider_call_ref、cost_status、partial/final 标识。

POST /projects/{id}/conversations 创建创作会话；POST /conversations/{id}/turns 发消息；GET /conversation-turns/{id}/events 流式事件；POST /conversation-turns/{id}/cancel 取消。分享 token 换取仅该版本的 experience_session，再创建 Guide 会话，不授予项目管理 API 权限。接口字段详见公共 API 补充。

## 任务

| 任务 ID | 内容 | 需求 | 依赖 |
|---|---|---|---|
| F11-T01 | 双模式 Session/Turn/DialogueProfile、上下文和证据权限 | F11-R01,F11-R02,F11-R03 | F01/F02/F06、F10 AgentProfile |
| F11-T02 | 真实模型流式与工具/引用、幂等、取消重连 | F11-R01,F11-R02,F11-R04 | F11-T01 |
| F11-T03 | Guide 场景/线索接入、未知与注入负测、模型动作白名单 | F11-R02,F11-R03,F11-R05 | F11-T02、F04/F08 版本权限 |
| F11-T04 | 独立预算/限流、会话保留删除、在线/离线差异和评估 | F11-R03,F11-R04,F11-R06 | F11-T02 |

失败时保留 turn 明确 failed/cancelled，不把截断文本当完整回答。撤销分享同步失效会话授权及后续回复读取；已经接收的文本无法抹除。离线资料版仅使用固定审核内容，禁用实时输入并解释需要在线服务。

