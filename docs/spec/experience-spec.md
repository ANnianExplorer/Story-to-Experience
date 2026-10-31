# ExperienceSpec v1 行为契约

> V2 产品已加入 AI 对话，参见 [F11](features/F11-ai-conversation.md)。本文件 1.0 仅定义确定性互动基座；对话通过版本化 DialogueProfile/ConversationBinding 伴随配置接入候选和发布清单。自然语言输出不直接写任务成功，也不纳入本文件的完全可达性证明。

结构权威：[experience-spec.schema.json](../../packages/contracts/experience-spec.schema.json)。当前运行时标识为 `1.0.0` 的**目标契约**，尚无已实现运行时。Schema 使用 Draft 2020-12，所有业务对象拒绝未知字段。结构与语义规则共同构成契约。

## 顶层与引用

顶层：schema_version、runtime_version、brief、source_snapshot_id、entry_scene、flags、claims、objectives、scenes、completion、asset_manifest。

| 对象 | 字段与意义 |
|---|---|
| brief | audience、duration_minutes、learning_goals；时长为目标，不作为状态计时器 |
| flags | id、initial=false；最多 12 个，运行中仅设 true |
| claims | 内部 id、source_claim_id/source_claim_revision、statement、content_type、evidence_span_ids；supported/legend 必有证据 |
| objectives | id、description、claim_ids |
| scenes | id、title、text、content_type、claim_ids、asset_ids、tasks、transitions；事实/传说场景正文须绑定事实 |
| completion | scene_id、required_flags；必须等于所有 required 任务的 completion_flag 集合 |
| asset_manifest | id、sha256、mime_type、license_note；不接受 URL/path 或可执行 SVG |

体验内部节点 ID 唯一且稳定，使用 ASCII 字母开头，后续字母/数字/下划线/连字符，最长 64。source_snapshot_id、source_claim_id、evidence_span_ids 是数据库业务 UUID；通过 source_claim_id+revision 将体验内部 claim 绑定回冻结事实。所有引用必须属于同一冻结源快照/版本。素材真正存储位置在服务端受控清单，模型不能指定路径。公开包另附允许展示的 evidence.json 与素材投影，不能直接导出原文库。

所有正文按纯文本渲染。语义层验证标签、task/option/transition ID 的唯一性、flag/claim/objective/scene/asset 引用、任务总数/条件深度、偏序无环和来源存在性。

## 条件与效果

条件采用唯一判别结构之一：`{"all":[...]}`、`{"any":[...]}`、`{"not":condition}`、`{"flag_equals":{"id":"flag","value":true}}`。all/any 至少一个元素、每组最多 12 项；最大嵌套深度 6。初始入口无需条件时可使用已声明初始 false 标记的 flag_equals=false，不使用空 all 作为隐式真。

效果仅 `{"set_flag":"declared_id","value":true}`。on_success 只能设置辅助标记，任务 completion_flag 只能由引擎在对应任务成功时自动设置，禁止其他任务或导航代为完成。无赋 false、脚本、表达式、次数解锁、随机判定、时钟或资源计数。重复设置 true 幂等。标记单调但条件允许 not，所以必须真的搜索死路，不能从单调性直接推断安全。

## 任务与动作

公共任务：id、type、label、required、completion_flag、objective_ids、claim_ids、requires、on_success、feedback、hints。每个任务有独占 completion_flag；required 任务必须有至少一个教学目标和一条 supported/legend 知识依据，不能仅用改编或待确认内容构成关键答案。全体验任务最多 12 项，其中必要任务 1—6，场景 4—6。每项非装饰任务的反馈引用必须覆盖答案所依赖的事实。

- hotspot：正常点击成功一次，设置 completion_flag 及 on_success。
- choice：options 含 id、label、correct、feedback、on_success，可带 target_scene；错误选项不设置标记或跳转。任务通过选项设置完成标记，再应用共同成功效果。
- sequence：items 2—6 个；precedence 至少一条 before/after/claim_id，判定为全部偏序边满足。输入先检查完整唯一排列，再判对错。
- transitions：场景独立导航动作 id、label、requires、target_scene。导航本身不设置任务标记。

体验参与者输入是受限联合：task 动作携 scene_id/task_id，choice 再携 option_id，sequence 再携 order；导航携 scene_id/transition_id。动作 ID 不是任意 JSON Pointer，不能从客户端直接提交状态。

## 原子执行顺序

1. 校验运行时/规格和输入；输入 scene_id 必须是当前场景，task/transition 必须属于该场景。
2. 校验 requires；任务 completion_flag 已为 true 时返回 ALREADY_COMPLETED，无额外效果。
3. 判定任务；无效输入返回 INVALID_ACTION，错误答案返回 WRONG_ANSWER；均保持 scene+flags 不变，仅产生反馈。
4. 在临时状态自动设置 completion_flag，合并允许的 on_success；choice 再应用该正确选项效果；均只设 true。
5. 计算最多一个显式目标；没有目标保持当前场景。跳入 completion.scene_id 时临时状态必须满足全部 required_flags，否则拒绝整个动作、无部分写入。
6. 一次性提交临时状态并输出反馈、结果码及只读状态。来源卡/提示展开/尝试计数不影响解锁，属于展示状态。
7. 完成场景为合法终止页，无任务和外跳；重玩重建初态。

ActionResult 至少含 result_code、next_state、feedback、completed；next_state 为 scene_id+flags。执行器不写日志/网络，由调用者写会话序号。刷新恢复须绑定 spec/runtime 哈希，发现旧会话不兼容则要求重玩，不偷偷迁移体验参与者进度。

## 排序独立预期

A<C、B<C，合法排列恰为 ABC、BAC；ACB、BCA、CAB、CBA 错误；AAB、AB、ABCD 是输入错误。必须用固定手工预期测试，而不是让同一个实现同时产生预期和实际。材料未规定 A/B 顺序不能补成 A<B。

## 状态验证目标

状态为 (scene_id, flags_bitset)。从初态 BFS 枚举所有有效动作产生的状态，错误答案/提示不扩展逻辑空间。排序最多枚举 6!=720 输入验证判定规则；状态边可压缩为成功/错误等价类。完成后反向搜索得到可到终态的集合。

技术状态检查必须证明：至少一个合格终态；全部可达非终态仍可到终态；全部完成态满足必要标记；必要任务存在可完成路径；偏序 DAG 有合法排列。预算到限为 inconclusive。该证明不表示体验参与者任意操作必然结束。

## 版本与哈希

schema_version 与 runtime_version 分开。v1 运行时只接受明确支持的 Schema 主版本；不兼容版本拒绝并保留内容，不进行静默修复。当前文件哈希按 [数据模型](data-model.md) 指定的规范字节计算。样例仅是人工合成工序教学占位，不作为任何真实非遗流程。

