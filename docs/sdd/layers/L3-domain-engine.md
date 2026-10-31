# L3 领域与共享引擎

> 范围：server/domain、packages/engine、packages/validator。当前为待实现设计。

## 职责

Python 领域建模 owner/project、SourceSnapshot、Claim、Blueprint、Run、Version、Review 与发布资格。TS 引擎独占体验参与者状态语义；TS validator 做跨引用、偏序和状态搜索。

## 数据流

applyAction(spec,state,input) 返回 next_state、feedback、result_code；输入不合法或答错不改变逻辑状态。API 调 TS 校验器只交换固定 JSON，不传代码或路径。

## 边界与禁止依赖

领域不得 import FastAPI、SQLAlchemy、LangGraph、模型 SDK；引擎不得 I/O、Date.now、随机数或 DOM。随机视觉效果不得影响判定。

## 实施细节与检查

逻辑状态为 scene_id + flags。任务 completion_flag 防重复效果；条件支持 not，标记单调不代表可完成性自动成立。新增状态维度必须更新枚举器、序列化与测试预期。

按 [分层目录](README.md) 核对上下游，功能落点见 [功能设计](../features/README.md)，真实门禁状态见 [质量目录](../../quality/gates.md)。

