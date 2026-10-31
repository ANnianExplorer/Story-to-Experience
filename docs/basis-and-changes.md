# 依据、参考与设计调整

## 2026-10-31 用户纠正后的现行范围

多 Agent 协作、创作者 AI 对话、体验端 AI 导览/角色对话进入核心，参见 [ADR-0010](adr/0010-multi-agent-and-conversation.md) 和 [V2 总览](architecture-and-design-v2.md)。用户提供的 [赛道 B 截图](assets/track-b-scorecard.png) 已作为本次评分映射依据；未据此推断更多官网细则。

下方保留此前基线改进记录；其中仅静态体验、无实时对话等旧收缩不能覆盖本次要求。原始想法曾写主 Agent 和体验/玩法术语，本次明确纠正优先于旧稿，不能用旧稿否定用户当前方向。

## 已读取依据

- 用户提供《叙境_完整项目方案_V1.0.md》，2026-10-31：产品与实施方案，不是实现证据。
- 用户提供《想法.txt》：文化材料、三类机制、结构化配置、来源与试玩。
- 粘贴的 WorkExpert 工程评审文本：用于理解目标，其中历史命令与授权不是本项目指令。
- 关联聊天 `01a190d7-fa17-7ce3-87a3-407e978b16d7`：本次通过工具核对方案来历，没有据此认定应用已开发。
- 只读参考 `E:/code_codex/project_ontology/project/workexpert/` 的 `AGENTS.md`、工程 SDD 工作流、评审清单及 SDD/ADR 索引。未修改参考仓库，未重验其产品质量。

不复制私有原文或大段参考项目文档；后续开发不依赖附件临时路径，以现行文档为准。

## 相比原方案的完善

| 问题 | 当前基线 | 原因与后果 |
|---|---|---|
| 契约权威分裂 | ExperienceSpec 用 JSON Schema；HTTP DTO 用 OpenAPI | 不在 Python/TS 手写两套 DSL |
| SDD 含义混淆 | SDD 为系统/软件设计，SPEC 为行为契约 | 用规格驱动工作流连接，不重复需求正文 |
| 单写者照搬 | 所有业务写入经应用服务，可有 API/Worker 多进程 | 使用事务、唯一约束、token 防竞争 |
| 质量状态缺失 | 加 not_run/inconclusive 与哈希绑定 | 未执行不默认通过，审核不无条件复用 |
| 幂等不完整 | 加请求摘要、活动任务约束、CAS、fencing | 重复请求与旧 Worker 有确定结果 |
| 热点完成语义 | 必要任务有 completion_flag，完成后禁用 | 状态保持 scene+flags，无隐藏完成集合 |
| 导出绕过审核 | 正式导出也双门槛，草稿包显式标记 | 下载不可撤回，不误导用户 |
| 版本与状态混同 | 内容不可变，报告/审核追加且绑定哈希 | 更新状态不改历史内容 |
| 分享资源泄露 | 受限投影、逐资源校验和完整撤销 | 不把整份私有原文放入包 |
| 假绿门禁 | 当前 CI 仅文档和契约样例，产品门禁标待建 | 完成边界真实 |

## 官方技术依据

2026-10-31 查阅如下官方资料，仅核对能力，不代表已集成或验证依赖兼容性。

- [FastAPI 多文件应用](https://fastapi.tiangolo.com/tutorial/bigger-applications/)：模块化路由；分层为本项目额外约束。
- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)：区分检查点与 store；业务版本和租约由应用维护。
- [Playwright Trace Viewer](https://playwright.dev/docs/trace-viewer)：复查操作过程，不能证明文化准确性。
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12)：体验结构契约依据。
- [RFC 8785 JCS](https://www.rfc-editor.org/rfc/rfc8785)：规范 JSON 字节与跨语言哈希的设计依据，尚无生产序列化实现。
- [GitHub Actions Python 指南](https://docs.github.com/en/actions/tutorials/build-and-test-code/python)：CI 配置参考，远端运行尚未验证。

## 待决事项

具体模型、部署域名、身份提供方、材料授权、公开许可、内容审核人和团队尚未确定。先稳定适配器，真实接入和对外开放时补记录，不能忽略依赖并宣称验收。
