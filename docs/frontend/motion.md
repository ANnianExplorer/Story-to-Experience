# React 动效、文字动画与微交互

## 实现选择

采用 CSS 处理 hover/focus/pressed 等简单效果，采用 [Motion for React](https://motion.dev/docs/react) 处理 React 挂载/退出、布局和场景转场；导入路径为 motion/react。React Bits 作为可审核的文字/微交互源码参考，不整库照搬。首版不同时引入 GSAP/重型 WebGL 动效栈。

时长、距离、缓动取 [Token](../../packages/ui/tokens.json)。参考视频中的抖色海浪默认转为轻量静态插画，避免工作台常驻逐像素运算。

## 动效目录

| 编号 | 场景/触发 | 效果与时长 | 限制 |
|---|---|---|---|
| M01 | 按钮 hover/pressed | 120ms；最多 -1px/0.98 scale | hover 仅精确指针；键盘 focus 同样清楚 |
| M02 | 面板/来源抽屉开关 | 280ms，最多 16px 淡入 | 即时管理焦点；关闭后回原入口 |
| M03 | 入口/章节短标题首次进入 | 480ms 字组淡入、最多 8px；stagger 45ms；总时长≤800ms | 每次场景进入只播一次，最多 8 组；正文不逐字打字 |
| M04 | 体验参与者切换场景 | 360ms 淡入，最多 16px | 引擎先提交；动画不控制解锁/胜负 |
| M05 | 线索获取/任务完成 | 180ms 底色/图标确认；最多 1.03 scale | 文本/状态立即出现，不等动画完成 |
| M06 | 排序卡片换位 | 200ms layout 过渡 | 保留焦点；键盘/上移下移同样可用 |
| M07 | 错误与待确认 | 200ms 反馈区出现 | 不用持续抖动/闪烁惩罚用户 |
| M08 | 加载/生成进度 | 真实阶段文字更新，必要时轻量指示 | 不伪造%/完成；减弱模式静态等待文字 |

动效只承载层级、因果和反馈；同一局部不叠加漂浮、弹跳、渐变扫描与粒子。无循环跑马标题、无光标追随作为必要操作、无强制平滑滚动或滚动劫持。装饰背景默认静态；确需循环时必须另有可停止控制和性能证据。

## 状态与动画严格解耦

动作提交立即调用 applyAction/API；以返回的真实状态渲染。不得在 onAnimationComplete 内设置完成标记、开始模型调用、晋级版本或解除提交锁。动画被取消、标签页隐藏或组件卸载时，业务状态仍正确。

React key 使用 scene/task 稳定 ID。AnimatePresence 的退出动画不得让旧场景继续接受提交；只读装饰 aria-hidden，离场交互内容需要立即不可操作。焦点切换至新场景标题/任务起点，别让视觉顺序和键盘顺序冲突。

文字分组使用 Intl.Segmenter 或等效 grapheme-safe 分段，兼容中文/组合字符/emoji。保留一个完整可访问标题，动画 span 标 aria-hidden，不能让读屏逐字重复。标题入场失败时内容保持可见，不能永久 opacity:0。

## 减弱模式

默认尊重 prefers-reduced-motion，并提供只保存在本地的“减少动效”设置。系统要求 reduce 时，本地选择不得重新启用运动。有效减弱 = 系统 reduce 或本地 reduce。

React 使用 [useReducedMotion](https://motion.dev/docs/react-use-reduced-motion) 配合 MotionConfig；但 MotionConfig 不替代项目自身的 CSS、文字分段和第三方 canvas 清理。减弱时移除平移/缩放/视差/逐组延迟，文字与关键反馈立即出现；仅确有必要时允许≤100ms 的淡变。持续粒子/背景视频不启动。

示意模式（需在未来 React 工具链中实际实现/类型检查，并从 Token 生成 preset，不能把这里的数字复制成另一事实源）：

```tsx
import type { ReactNode } from "react";
import { motion, useReducedMotion, type MotionProps } from "motion/react";

type ScenePanelProps = {
  sceneId: string;
  children: ReactNode;
  localReduce: boolean;
  presets: { scene: Pick<MotionProps, "initial" | "animate" | "transition"> };
};

function ScenePanel({ sceneId, children, localReduce, presets }: ScenePanelProps) {
  const systemReduce = useReducedMotion();
  const reduce = Boolean(systemReduce || localReduce);
  return (
    <motion.section
      key={sceneId}
      initial={reduce ? false : presets.scene.initial}
      animate={presets.scene.animate}
      transition={reduce ? { duration: 0 } : presets.scene.transition}
    >
      {children}
    </motion.section>
  );
}
```

此代码仅说明职责，不是已构建的生产组件；完整 props 类型、语义标题/焦点、退出与禁用逻辑由 F04-T04 验收。

## 性能与离线

优先 transform/opacity；不逐帧改变 top/left/width 或整页 filter。大 blur、噪点 canvas 和视频不进入工作台常驻布局；动画离开视口/页面隐藏停止，卸载清理 observer/RAF/listener。SSR/静态包无 JS 时仍能看到内容。

首个实现建立真实手机与 Chromium trace 基线，目标设备上的响应由实际测量决定。新增首屏动效 JS gzip 预算初值≤40KiB（包含该动效直接增加的运行时代码，不含 React 基座）；超额先简化并记录，不凭示例视频承诺 60fps。生产包本地提供必要资产，静态导出断网可用。

