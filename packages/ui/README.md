# 共享前端视觉基础

数值权威为 [tokens.json](tokens.json)，样式由 [check_ui.py](../../scripts/check_ui.py) 派生为 [tokens.css](tokens.css)。修改 JSON 后执行 `python scripts/check_ui.py --write`，再无参数运行以验证生成一致性、指定对比度和动效上界。

生产 React primitives、patterns 和 motion presets 后续按 [前端规范](../../docs/frontend/README.md) 实施；本目录当前不是已发布或已安装的组件库。样式预览只用于审阅视觉和反馈，不承载业务数据。
