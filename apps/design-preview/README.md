# 叙境动态设计预览

这是针对用户“静态稿仍有模板感、动态不明显”的第二轮试作。实际使用 React、TypeScript 与 Motion，保持海盐与纸页配色，采用非对称纸页、衬线标题、图版注记和开放分栏，移除等宽卖点卡片。

## 查看和构建

直接打开生成的 [独立动态预览](../../docs/frontend/style-preview.html)，文件已内置 React、Motion、样式和原创图版，无需本地服务器或联网 CDN。

在本目录执行：

```powershell
npm ci --ignore-scripts --registry https://registry.npmjs.org
npm run check
npm run build
npm test
node build.mjs --check
```

依赖的精确版本在 package.json/package-lock.json。build.mjs 将源码和中央 Token 编译为独立 HTML，禁止手改生成文件。图形为本项目原创 SVG 试作，第三方代码许可保留在构建输出的注释中。

## 可实际操作

文字裁切入场和重播、章节切换和图版转场、线索点击/摘记出现、来源抽屉/焦点管理、排序拖动/上下按钮/有效与错误反馈、工作台切换、系统及本地减少动效。

排序只演示合成规则 A<C、B<C，支持 ABC/BAC。这里的 React 本地状态仅服务设计预览，不能作为生产 ExperienceSpec 引擎。没有 API、真实模型或业务发布。所有业务功能仍按功能登记表保持 planned。

## 验证边界

类型检查和独立文件构建验证实际源码；jsdom 集成测试运行构建产物的真实 React/Motion，检查线索、来源/焦点、按钮排序和减弱状态。jsdom 不具备真实布局/触屏/原生拖拽/完整渲染能力，不能以这些测试宣称手机、拖拽手感或动画帧率已验收。

构建另计算完整 JS gzip 与仅 React 基座 gzip 的差值，作为动效+本试作代码的增量体积估计；不是手机性能数据。实际结果见 [第二轮报告](../../docs/quality/reports/2026-10-31-frontend-v2.md)。
