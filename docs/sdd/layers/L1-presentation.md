# L1 展示与接入

> 范围：apps/workbench、apps/player、apps/api 的路由与 DTO。当前为待实现设计。

## 职责

工作台提供项目列表、材料/来源、预览、生成/修改、测试/费用抽屉；体验运行端提供任务、提示、出处与复盘。HTTP 路由负责身份、输入和错误映射，随后调用应用用例。

## 数据流

UI → 生成客户端 → HTTP → application；player → engine → 新状态 → React 渲染。SSE 断线按 sequence 补事件；断档先取快照再订阅。

## 边界与禁止依赖

禁止浏览器 import 文件系统、数据库和 Provider；禁止通过隐藏按钮替代权限。iframe 预览独立来源，不通过 postMessage 暴露密钥。

## 实施细节与检查

主题、响应式和 React 动效统一取 [前端规范](../../frontend/README.md)。Token 负责数值，功能状态机负责行为；动画展示状态不成为任务/权限第二事实源。

空材料、解析失败、等待补充、取消、预算停止、技术未知、待审和冲突均需独立可理解状态。排序提供上移/下移与键盘；移动端/屏幕阅读标签进入 F04/F09 验收。

按 [分层目录](README.md) 核对上下游，功能落点见 [功能设计](../features/README.md)，真实门禁状态见 [质量目录](../../quality/gates.md)。

