# 共享前端视觉基础

数值权威为 [tokens.json](tokens.json)，样式由 [check_ui.py](../../scripts/check_ui.py) 派生为 [tokens.css](tokens.css)。修改 JSON 后执行 `python scripts/check_ui.py --write`，再无参数运行以验证生成一致性、指定对比度和动效上界。

生产 React primitives、patterns 和 motion presets 后续按 [前端规范](../../docs/frontend/README.md) 实施；本目录当前不是已发布或已安装的组件库。样式预览只用于审阅视觉和反馈，不承载业务数据。

## 古典编辑层（classical.css）

[classical.css](classical.css) 是两个前端共用的**版式语言**，不是第二套主题：

- 只引用 `tokens.css` 的 `--xj-*` 变量，不声明任何颜色/尺寸字面量。
- 提供 `.xj-display`（衬线大字）、`.xj-quote`（楷体引文）、`.xj-kicker`（等宽注记）、
  `.xj-index`（章目编号 + 细线）、`.xj-seal`（朱文印）、`.xj-vertical`（竖排题签）、
  `.xj-frame`（双细线书框）、`.xj-grain`（纸颗粒，用 `color-mix` 由墨色生成）。
- 参考方向来自用户指定的 kigo.studio：大字编辑式排版、暗场、编号细线，
  转译为宣纸底、墨色、朱印、鎏金细线与册页留白；不复制参考站点的素材或文案。

`python scripts/check_ui.py` 现在同时检查三件事：Token 对比度与动效上界、
手写样式表中**不得出现颜色字面量**、以及**不得引用未定义的 `--xj-*` 变量**
（未定义变量会让样式在浏览器里静默失效，截图验收曾因此发现按钮被压扁）。
