# 组件、状态与前端组织

## 目录与依赖

已有 Token、派生 CSS，以及独立 React/Motion [设计试作](../../apps/design-preview/README.md)；下面生产组件目录仍是后续实现目标：

```text
packages/ui/
  tokens.json                  已有：唯一数值源
  tokens.css                   已有：派生
  src/primitives/              待建：Button/Field/Dialog/Tabs
  src/patterns/                待建：StatusBadge/SourceCard/StageTimeline
  src/motion/                  待建：统一 MotionProvider/presets
apps/workbench/src/
  app/                         路由、Provider 与布局组合
  features/{projects,sources,generation,versions,review}/
  services/                    派生客户端、SSE 连接；无业务状态副本
apps/experience/src/
  app/
  components/{scene,task,evidence,recap}/
  adapters/                    规格载入、会话存储与引擎桥接
```

共享 UI 仅依赖 React、公共类型和展示辅助逻辑，不 import 工作台、API 服务或引擎内部实现。主题/动效组件不持有项目权限；体验运行端适配层调用共享引擎，组件不另写一份答案规则。

服务端状态与本地展示状态分离：任务、质量和版本来自 API/事件；选中标签、抽屉展开和本地文字输入属于 UI；体验参与者 scene/flags 只由引擎生成。初版 React 状态与 context 足够时不提前引入全局 store；如确有复杂同步需求再做决策。

## 核心组件契约

| 组件 | 必须呈现的内容与行为 |
|---|---|
| Button/IconButton | default/hover/focus/pressed/pending/disabled；pending 防重复提交但保留动作名称；真实 button |
| Field/TextArea | label、说明、错误、字数限额；错误 id 与 aria-describedby 关联；失败保留值 |
| StatusBadge | 文字+可区分图标；technical/content/lifecycle 分开，不用统一“完成”掩盖待审 |
| SourceCard/EvidenceDrawer | 来源标题、定位、引文、性质和许可；展开只改展示；不把全文公开投影 |
| StageTimeline | 仅按持久事件显示阶段；未知总进度显示阶段名，不虚构百分比 |
| VersionDiff | 基准/候选、影响范围和审核失效；409 明确重载，不丢修改输入 |
| ChoiceOption | 键盘/触控；结果由引擎；正确/错误文字反馈而非只有颜色 |
| SequenceCard | 拖动+上移/下移；保持焦点，位置变化可读播报；有明确提交 |
| FeedbackPanel | 立即显示结果与解释/出处；动效不延迟知识反馈 |
| Toast/Dialog | 普通结果 role=status；关键错误按需要 role=alert，避免重复播报；弹层有焦点管理 |

不以营销式假指标填充面板。已发生费用、估算和未知分别显示；修复次数、调用次数取真实记录。空态可有小型器物插画，但正文说明下一步，不能强制玩小游戏才能返回。

## 组件基座与第三方

基础控件可采用经过确认的 shadcn/ui/headless primitives，必须套本项目 Token 并验证键盘、焦点和状态，不直接保留默认主题。React Bits 仅按需引入少量文字/微交互实现，记录源路径/版本/许可/依赖；通过 reduced motion、卸载清理和移动性能检查后成为项目组件。

依赖版本与许可证在首次 React 代码提交锁定。当前不增加未安装的生产依赖，也不把样式预览写成组件已经实现。

