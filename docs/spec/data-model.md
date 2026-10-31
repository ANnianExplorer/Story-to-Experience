# 数据模型、哈希与迁移契约

> PostgreSQL 目标模型，尚无迁移或已部署数据库。外键、唯一约束和提交条件需要实际迁移/竞争测试，不能只在应用里约定。

## 核心表

| 表 | 必需字段/约束 |
|---|---|
| projects | id,owner_id,name,brief_json,brief_revision,revision_head_id,selected_version_id,stable_version_id,active_revision_run_id；指针版本同项目 |
| source_documents | id,project_id,sha256,storage_key,mime_type,license_note,parse_status,parse_version；文件键由服务生成 |
| source_spans | id,source_id,parse_version,page,paragraph,start_cp,end_cp,quote,normalized_text_hash；半开区间 |
| claims | id,project_id,revision,statement,content_type；事实修改生成新 revision |
| claim_evidence | claim_id,claim_revision,span_id；复合唯一且同项目 |
| source_snapshots | id,project_id,manifest_json,sha256；固定文档/解析/片段/事实 revision |
| blueprints | id,project_id,snapshot_id,brief_revision,payload,sha256,parent_id；不可变 |
| experience_versions | id,project_id,parent_id,run_id,step_key,content_json,spec_hash,semantic_hash,manifest_hash,runtime_version；UNIQUE(run_id,step_key) |
| runs | id,project_id,kind,status,stage,base_version_id,input_hash,attempt,lease_owner,lease_expires_at,fencing_token,active_ms,counters |
| run_steps | id,run_id,step_key,input_hash,stage_version,output_hash,output_ref,token；UNIQUE(run_id,step_key,input_hash,stage_version) |
| run_events | run_id,sequence,type,payload,created_at；PRIMARY KEY(run_id,sequence) |
| model_calls | id,run_id,provider,model,provider_request_id,attempt,status,usage,currency,cost,cost_status,started_at,finished_at |
| budget_reservations | id,run_id,call_id,reserved_amount,state；call_id 唯一；结算不能双扣或双释放 |
| validation_reports | id,version_id,spec_hash,source_hash,runtime_hash,asset_hash,checker_version,layer,status,evidence_manifest |
| content_reviews | id,version_id,semantic_hash,reviewer_id,decision,notes,reused_from,created_at；追加不可覆盖 |
| review_items | review_id,claim_revision/task_id,decision,note；覆盖范围可计算 |
| artifacts | id,project_id,version_id,kind,hash,storage_key,visibility,license_note |
| shares | id,project_id,version_id,token_hash,expires_at,revoked_at；token_hash 唯一，原 token 不落日志 |
| exports | id,project_id,version_id,mode,status,artifact_id,manifest_hash；ready 前重验资格 |
| idempotency_requests | actor_id,scope,key,request_hash,run_id,response_json；复合唯一 |

必要索引包括 owner+project 列表、project+created_at 版本、可抢占 status+lease_expires_at、run+sequence。活动任务使用部分唯一索引 project_id WHERE kind IN (generate,revision) AND status IN (queued,running,waiting_input)。资料解析可独立任务，但不得绕过总材料限额。

## 不可变范围

版本内容 JSON、输入快照、蓝图、原文解析结果与素材哈希不可覆盖。technical/content 状态由当前有效报告与审核投影得出，可缓存到单独质量投影表；不能修改原始版本体来更新状态。报告与审核追加，保留历史失败和撤回。

引用同项目要靠复合外键(project_id,id)或同等事务约束，不是先查归属后无条件写 ID。父版本同项目；稳定版本资格在锁项目行的事务中重新验证。

## 文本与哈希

原文规范化仅做换行 CRLF/CR→LF、Unicode NFC；不折叠空格或删除正文。偏移为规范化字符串 Unicode 码点半开区间，保留原 PDF 页/段映射；TS 来源定位不得直接用 UTF-16 索引替代。

文件 sha256 作用于原始字节；spec_hash 作用于服务端冻结的规范 JSON UTF-8 字节：采用 RFC 8785 JCS 兼容规范序列化，DSL 仅允许整数/字符串/布尔，禁止 NaN/Infinity。规范化完成后保存原规范字节，各语言对相同字节取哈希，不各自 pretty-print 再算。签入 JCS 库前验证排序、转义、Unicode 和跨语言 golden fixtures。

semantic_hash 的投影规则必须版本化：包含事实及证据、目标、全部叙事/反馈/提示文字、任务/规则；仅排除纯主题样式和非语义素材展示参数。不能简单以字段名 text 排除。语义投影实现未落地前一律不复用审核。

## 关键事务

提交 run 同事务登记幂等键、占活动任务和写首事件。阶段提交锁 run 行核验 token/lease/status，再插 run_step、候选和事件。取消抢同一锁并使 token 失效。分配 sequence 必须锁 run 计数器或等效原子机制，不能 SELECT MAX+1 无锁。

预算预留锁 run 预算行，核对当前已发生+未结预留+新请求不超上限；未知费用预留不无条件释放。完成阶段更新修订头/候选指针，stable 仅独立资格用例修改。

文件先临时写入并验哈希，原子发布后提交数据库引用；失败可留下孤儿，按无引用与保留期回收。删除文件必须确认无版本/报告/审核引用并满足隐私策略。

## 迁移与回滚

迁移用 Alembic 版本化，首个数据库提交固定实际工具版本。新增可空字段→回填→校验→切读→再约束；破坏性收缩不能与新代码首次发布同时做。回退应用前核验旧代码是否能读当前 Schema；不能读取则恢复备份到隔离环境验证后切换，不盲目 down migration。

备份需数据库、文件、runtime/Schema、manifest 与配置版本。恢复后校验版本/来源/报告哈希和固定离线体验；没有真实演练不算可恢复。许可证撤销/隐私删除可能要求撤销分享、删除内容并保留最小审计墓碑，不能以“不可变”为由永久保留用户已要求删除的私有原文。

## V2 新增 Agent 与会话实体（目标模型）

| 表／记录 | 主要约束 |
|---|---|
| agent_tasks | run_id、parent_task_id、agent_id/profile_version、dependencies、input_hash、status、token、budget_ref；同输入/角色/任务结果幂等 |
| agent_artifacts | task_id、project_id、schema_version、artifact_hash/ref、citation_refs；不可变、同项目 |
| agent_handoffs / agent_reviews | 交接来源/目标/原因与模型审校问题；不能代替人工批准 |
| dialogue_profiles | profile_version、角色与改编说明、公开证据范围、目标/提示/动作策略；冻结哈希 |
| conversation_sessions | creator/guide、actor 或 experience_session、project_id、version_id、profile_hash、status、expires_at；作用域不漂移 |
| conversation_turns | session_id、client_turn_id、request_hash、context_hash、status、sequence、provider_call_ref、partial/final、usage；唯一活动 turn 与幂等键 |
| conversation_messages / citations | turn_id、角色、允许保留的文本、稳定出处引用；权限与删除策略随会话 |
| context_snapshots | 事实锚点、摘要/检索策略版本、消息窗口、场景/线索与来源哈希；不能用摘要覆盖权威事实 |

shares 增加允许动作及会话策略，experience_sessions 仅允许固定版本读取/Guide 对话。版本清单增加 DialogueProfile/ConversationBinding 哈希；这不改变旧结构化任务内容。后端迁移仍待实现，不把此表当已经存在的 Schema。

语义哈希投影同时纳入 DialogueProfile 的角色改编、事实范围、教学目标、提示/动作策略和提示词版本。改变这些内容使相关审核失效；动态聊天文本单独记录，不回写为不可变来源或被审核事实。

