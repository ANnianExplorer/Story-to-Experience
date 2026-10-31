import React, { useEffect, useRef, useState, type RefObject } from 'react';
import { createRoot } from 'react-dom/client';
import {
  AnimatePresence, LazyMotion, MotionConfig, domAnimation, m,
  useIsPresent, useReducedMotion,
} from 'motion/react';
import tokens from '../../../packages/ui/tokens.json';
import './style.css';

type Step = 0 | 1 | 2;
type Piece = 'A' | 'B' | 'C';
type Result = 'idle' | 'valid' | 'invalid';
const ease = tokens.motion.ease as [number, number, number, number];
const seconds = (name: keyof typeof tokens.motion.duration_ms) => tokens.motion.duration_ms[name] / 1000;

const chapters = [
  { no: '01', name: '看见器物', title: ['先看看，', '故事从哪里开始。'], text: '一件器物，一页记录。把目光停在细节里，线索会告诉你下一步。' },
  { no: '02', name: '找到依据', title: ['每一条线索，', '都有它的来处。'], text: '故事可以改编，答案需要依据。翻开材料，看看这一次行动为什么成立。' },
  { no: '03', name: '理清先后', title: ['顺序，', '也可以不止一种。'], text: '材料只要求 A 和 B 都在 C 前。亲手调整一下，再看看哪些排列同样成立。' },
] as const;

function Arrow({ back = false }: { back?: boolean }) {
  return <svg className="arrow" viewBox="0 0 32 20" aria-hidden="true" style={back ? { transform: 'rotate(180deg)' } : undefined}><path d="M1 10h27M20 2l8 8-8 8" /></svg>;
}

function FieldDrawing({ step, replay, reduce }: { step: Step; replay: number; reduce: boolean }) {
  const stroke = { initial: reduce ? false as const : { pathLength: 0 }, animate: { pathLength: 1 }, transition: { duration: reduce ? 0 : seconds('title'), ease } };
  return <svg className="field-drawing" viewBox="0 0 620 590" aria-hidden="true" key={`drawing-${step}-${replay}`}>
    <defs>
      <pattern id="print-grain" width="6" height="6" patternUnits="userSpaceOnUse"><circle cx="1" cy="2" r=".65" fill="currentColor" opacity=".2" /><circle cx="4" cy="5" r=".45" fill="currentColor" opacity=".12" /></pattern>
      <pattern id="crosshatch" width="7" height="7" patternUnits="userSpaceOnUse"><path d="M0 7L7 0M-2 2L2-2M5 9L9 5" stroke="currentColor" strokeWidth=".65" opacity=".28" /></pattern>
    </defs>
    <g className="contour">
      {[0, 1, 2, 3, 4, 5, 6].map(i => <m.path key={i} {...stroke} d={`M${28 + i * 7} ${295 + i * 12}C140 ${190 + i * 8} 190 ${410 + i * 4} 325 ${300 + i * 9}S450 ${215 + i * 13} 596 ${290 + i * 9}`} />)}
    </g>
    <m.g animate={{ rotate: step === 0 ? -4 : step === 1 ? 1 : -2 }} style={{ transformOrigin: '310px 300px' }} transition={{ duration: reduce ? 0 : seconds('scene'), ease }}>
      <path className="object-shadow" d="M177 415c39-28 171-29 219 1s-22 49-96 47-159-23-123-48Z" />
      <path className="vessel-fill" d="M252 134c-8 38-8 63-24 81-34 37-47 63-43 110 4 48 35 95 112 95 81 0 116-39 118-97 1-44-19-77-46-108-16-19-16-50-19-81Z" />
      <path className="vessel-hatch" d="M252 134c-8 38-8 63-24 81-34 37-47 63-43 110 4 48 35 95 112 95 81 0 116-39 118-97 1-44-19-77-46-108-16-19-16-50-19-81Z" />
      <m.path className="object-outline" {...stroke} d="M252 134c-8 38-8 63-24 81-34 37-47 63-43 110 4 48 35 95 112 95 81 0 116-39 118-97 1-44-19-77-46-108-16-19-16-50-19-81Z" />
      <ellipse className="vessel-rim" cx="301" cy="133" rx="51" ry="14" />
      <path className="object-outline" d="M199 286c53 18 139 19 200-2m-205 17c58 20 143 20 209-4m-197 61c48 13 132 14 187-1" />
      <path className="object-fine" d="M223 248c-17 30-19 56-10 91m139-155c10 31 35 58 39 88m-169 91c14 21 29 30 55 35" />
    </m.g>
    <g className="measurement"><path d="M143 164v245m-7-245h14m-14 245h14M244 455h119m-119-7v14m119-14v14" /><text x="113" y="286" transform="rotate(-90 113 286)">OBSERVATION / X</text></g>
    <circle className="sun" cx="472" cy="105" r="37" />
    <rect x="176" y="118" width="245" height="310" fill="url(#print-grain)" opacity=".3" />
    <g className="annotation"><path d="M420 218q44-6 64 23m-3-9 3 9-10-1" /><text x="425" y="195">观察这里</text><text x="424" y="211" className="annotation-small">a detail to begin with</text></g>
  </svg>;
}

function PreviewView({ children, className, reduce }: { children: React.ReactNode; className: string; reduce: boolean }) {
  const present = useIsPresent();
  return <m.section className={className} inert={!present} initial={reduce ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: reduce ? 0 : seconds('scene'), ease }}>{children}</m.section>;
}

function Evidence({ close, origin, reduce }: { close: () => void; origin: RefObject<HTMLElement | null>; reduce: boolean }) {
  const panel = useRef<HTMLElement>(null);
  const present = useIsPresent();
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const returnTarget = origin.current;
    document.body.style.overflow = 'hidden';
    panel.current?.querySelector<HTMLButtonElement>('button')?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); close(); }
      if (event.key !== 'Tab') return;
      const controls = Array.from(panel.current?.querySelectorAll<HTMLElement>('button, a[href], [tabindex="0"]') ?? []);
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener('keydown', onKey);
    return () => { document.body.style.overflow = previousOverflow; document.removeEventListener('keydown', onKey); returnTarget?.focus(); };
  }, [close, origin]);
  return <m.div className="evidence-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: reduce ? 0 : seconds('base') }} inert={!present} onClick={close}>
    <m.aside ref={panel} className="evidence-sheet" role="dialog" aria-modal="true" aria-labelledby="evidence-heading" initial={reduce ? false : { x: 16, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: reduce ? 0 : 16, opacity: 0 }} transition={{ duration: reduce ? 0 : seconds('panel'), ease }} onClick={event => event.stopPropagation()}>
      <div className="sheet-top"><span>原文摘记 / 001</span><button className="plain close" onClick={close} aria-label="关闭来源">×</button></div>
      <p className="eyebrow">THE SOURCE, NOT THE WHOLE STORY</p>
      <h2 id="evidence-heading">先有依据，<br />再有故事。</h2>
      <blockquote>“工具 X 用于观察。<br />A 先于 C；B 先于 C。<br />未规定 A 与 B 的相对顺序。”</blockquote>
      <p>来源：合成教学材料，第 1—2 段。</p>
      <p className="muted">这是一段工程演示文本，不对应真实工艺。你看到的器物插图仅用于探索交互和视觉风格的试作。</p>
      <div className="evidence-foot"><span>材料支持 / 合成样例</span><button className="text-action" onClick={close}>回到刚才的地方 <Arrow back /></button></div>
    </m.aside>
  </m.div>;
}

function SortTrial({ reduce }: { reduce: boolean }) {
  const [order, setOrder] = useState<Piece[]>(['C', 'A', 'B']);
  const dragged = useRef<Piece | null>(null);
  const [result, setResult] = useState<Result>('idle');
  const [announcement, setAnnouncement] = useState('可拖动，也可以用上下按钮调整。');
  const reorder = (next: Piece[]) => { setOrder(next); setResult('idle'); };
  const move = (piece: Piece, direction: -1 | 1) => {
    const next = [...order], from = next.indexOf(piece), to = from + direction;
    if (to < 0 || to >= next.length) return;
    [next[from], next[to]] = [next[to], next[from]];
    reorder(next); setAnnouncement(`步骤 ${piece} 已移至第 ${to + 1} 位。`);
  };
  const submit = () => {
    const valid = order.indexOf('A') < order.indexOf('C') && order.indexOf('B') < order.indexOf('C');
    setResult(valid ? 'valid' : 'invalid');
    setAnnouncement(valid ? '这个排列成立。A 和 B 都在 C 前，A、B 之间的顺序由你决定。' : '再看一眼材料：A 和 B 都要在 C 前。可以继续调整。');
  };
  return <div className="sort-trial">
    <div className="sort-caption"><span>排列练习</span><span>合成规则 / A、B → C</span></div>
    <ul className="sort-list" aria-label="排列合成步骤">
      {order.map((piece, index) => <m.li key={piece} initial={false} animate={{ y: index * 80 }} transition={{ duration: reduce ? 0 : seconds('base'), ease }} className="sort-slot">
        <div className="sort-piece" draggable={!reduce} onDragStart={event => {
          if ((event.target as HTMLElement).closest('button')) { event.preventDefault(); return; }
          dragged.current = piece;
          event.dataTransfer.effectAllowed = 'move';
          event.dataTransfer.setData('text/plain', piece);
        }} onDragOver={event => { if (dragged.current) event.preventDefault(); }} onDragEnd={() => { dragged.current = null; }} onDrop={event => {
          event.preventDefault();
          const source = dragged.current;
          if (!source || source === piece) return;
          const next = order.filter(item => item !== source);
          next.splice(index, 0, source);
          reorder(next); setAnnouncement(`步骤 ${source} 已移至第 ${index + 1} 位。`);
          dragged.current = null;
        }}><span className="piece-letter">{piece}</span><span className="piece-description">{piece === 'C' ? '最后完成的步骤' : 'C 的前置步骤'}</span><span className="piece-controls"><button disabled={index === 0} onClick={() => move(piece, -1)} aria-label={`上移步骤 ${piece}`}>↑</button><button disabled={index === order.length - 1} onClick={() => move(piece, 1)} aria-label={`下移步骤 ${piece}`}>↓</button></span></div>
      </m.li>)}
    </ul>
    <div className="sort-bottom"><button className="text-action" onClick={submit}>看看这个顺序 <Arrow /></button><span className={`result-mark ${result}`} aria-hidden="true">{result === 'valid' ? '✓' : result === 'invalid' ? '再试一次' : ''}</span></div>
    <p className={`sort-message ${result}`} role="status">{announcement}</p>
  </div>;
}

function App() {
  const systemReduce = useReducedMotion();
  const [localReduce, setLocalReduce] = useState(false);
  const reduce = Boolean(systemReduce || localReduce);
  const [mode, setMode] = useState<'experience' | 'workbench'>('experience');
  const [step, setStep] = useState<Step>(0);
  const [collected, setCollected] = useState(false);
  const [replay, setReplay] = useState(0);
  const [evidence, setEvidence] = useState(false);
  const origin = useRef<HTMLElement | null>(null);
  const chapter = chapters[step];
  const openEvidence = (event: React.MouseEvent<HTMLButtonElement>) => { origin.current = event.currentTarget; setEvidence(true); };
  const closeEvidence = React.useCallback(() => setEvidence(false), []);
  const selectStep = (next: Step) => { setStep(next); };
  return <LazyMotion features={domAnimation} strict><MotionConfig reducedMotion={reduce ? 'always' : 'never'} transition={{ duration: reduce ? 0 : seconds('base'), ease }}>
    <div className="paper-app" data-motion={reduce ? 'reduce' : 'full'}>
      <header className="masthead"><a href="#" className="wordmark" aria-label="叙境首页" onClick={event => { event.preventDefault(); setMode('experience'); setStep(0); }}>叙境<span>STORY / EXPERIENCE</span></a>
        <nav aria-label="预览视图">{(['experience', 'workbench'] as const).map(view => <button key={view} className="plain nav-item" aria-pressed={mode === view} onClick={() => setMode(view)}>{view === 'experience' ? '体验小样' : '创作工作台'}{mode === view && <m.span className="nav-line" initial={reduce ? false : { scaleX: 0 }} animate={{ scaleX: 1 }} style={{ transformOrigin: 'left' }} transition={{ duration: reduce ? 0 : seconds('panel'), ease }} />}</button>)}</nav>
        <div className="mast-controls"><button className="plain motion-toggle" onClick={() => setLocalReduce(!localReduce)} aria-pressed={reduce} disabled={Boolean(systemReduce)}>{systemReduce ? '系统已减少动效' : reduce ? '动效 · 已减少' : '动效 · 开启'}</button><button className="plain replay" onClick={() => setReplay(value => value + 1)} aria-label="重播入场动效">↻</button></div>
      </header>
      <main>
        <AnimatePresence initial={false} mode="wait">
          {mode === 'experience' ? <PreviewView key="experience" className="experience" reduce={reduce}>
            <div className="margin-note"><span>FIELD NOTES / 2026</span><span>一次五分钟的探索</span></div>
            <div className="editorial-hero">
              <div className="hero-copy"><p className="eyebrow"><span className="tiny-line" />{chapter.no} — {chapter.name}</p>
                <h1 aria-label={chapter.title.join('')} key={`title-${step}-${replay}`}>
                  {chapter.title.map((line, index) => <span className="title-mask" key={line} aria-hidden="true"><m.span initial={reduce ? false : { clipPath: 'inset(0 0 100% 0)', y: 8, opacity: 0 }} animate={{ clipPath: 'inset(0 0 0% 0)', y: 0, opacity: 1 }} transition={{ duration: reduce ? 0 : seconds('title'), delay: reduce ? 0 : index * tokens.motion.stagger_ms / 1000, ease }}>{line}</m.span></span>)}
                </h1>
                <AnimatePresence mode="wait" initial={false}><m.p key={step} className="hero-description" initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: reduce ? 0 : seconds('base') }}>{chapter.text}</m.p></AnimatePresence>
                <div className="hero-actions">{step === 0 ? <button className="round-action" onClick={() => selectStep(1)}><span>拾起一条线索</span><span className="action-disc"><Arrow /></span></button> : step === 1 ? <button className="round-action" onClick={openEvidence}><span>翻开原文</span><span className="action-disc"><Arrow /></span></button> : <button className="round-action" onClick={() => selectStep(0)}><span>再从头走一遍</span><span className="action-disc"><Arrow back /></span></button>}</div>
                <div className="pencil-note">慢一点，<br />让细节自己说话。<span aria-hidden="true">↗</span></div>
              </div>
              <div className={`field-plate step-${step}`}>
                <m.div className="blue-print" animate={{ rotate: step === 0 ? 2 : step === 1 ? -1 : 1, x: step === 1 ? 8 : 0 }} transition={{ duration: reduce ? 0 : seconds('scene'), ease }}><span className="print-label">一件器物的观察记录</span><span className="large-watermark" aria-hidden="true">物</span></m.div>
                <m.div className="study-sheet" animate={{ rotate: step === 0 ? -3 : step === 1 ? 0 : -1.5, y: step === 1 ? -8 : 0 }} transition={{ duration: reduce ? 0 : seconds('scene'), ease }}>
                  {step === 2 ? <SortTrial reduce={reduce} /> : <><FieldDrawing step={step} replay={replay} reduce={reduce} /><div className="plate-caption"><span>NO. 001 / 练习用器物 X</span><span>观察图 · 非实物档案</span></div>
                    <m.button className={`hotspot ${collected ? 'collected' : ''}`} aria-label={collected ? '查看已收集线索' : '收集器物线索'} onClick={() => { setCollected(true); setStep(1); }} whileHover={reduce ? undefined : { scale: 1.03 }} whileTap={reduce ? undefined : { scale: 0.98 }}><span>{collected ? '✓' : '+'}</span><span>{collected ? '线索已找到' : '找到一条线索'}</span></m.button></>}
                </m.div>
                <AnimatePresence>{step === 1 && <m.div key="evidence-slip" className="evidence-slip" initial={reduce ? false : { y: 16, opacity: 0, rotate: -2 }} animate={{ y: 0, opacity: 1, rotate: 2 }} exit={{ opacity: 0 }} transition={{ duration: reduce ? 0 : seconds('panel'), ease }}><span className="slip-number">摘记 / 01</span><p>“工具 X 用于观察。”</p><button className="plain slip-link" onClick={openEvidence}>来源 · 第 1 段 <span aria-hidden="true">↗</span></button></m.div>}</AnimatePresence>
                <div className="rubber-stamp" aria-hidden="true">叙境<br /><span>试作小样</span></div>
              </div>
            </div>
            <div className="chapter-rail" aria-label="体验章节">{chapters.map((item, index) => <button key={item.no} className={`chapter ${step === index ? 'active' : ''}`} aria-current={step === index ? 'step' : undefined} onClick={() => selectStep(index as Step)}><span className="chapter-index">{item.no}</span><span>{item.name}</span><span className="chapter-end" aria-hidden="true">{step === index ? '↗' : '→'}</span>{step === index && <m.span className="chapter-line" initial={reduce ? false : { scaleX: 0 }} animate={{ scaleX: 1 }} style={{ transformOrigin: 'left' }} transition={{ duration: reduce ? 0 : seconds('scene'), ease }} />}</button>)}</div>
            <div className="bottom-note"><span role="status">{collected ? '✓ 已拾取 1 条合成线索，可翻原文核对。' : '观察、收集、排序。知识从行动里发生。'}</span><span>所有内容均为合成教学样例。</span></div>
          </PreviewView> : <PreviewView key="workbench" className="workbench" reduce={reduce}>
            <div className="workbench-heading"><div><p className="eyebrow">PROJECT / 001</p><h1>把一页材料，<br />慢慢变成一段体验。</h1></div><span className="work-label">草稿 · 内容待审核</span></div>
            <div className="work-canvas"><aside className="work-sources"><div className="column-label">01 / 材料与依据</div><h2>合成教学材料</h2><p className="muted">1 份文本 · 3 条事实</p><div className="source-lines"><p>工具 X 用于观察。</p><p>A 先于 C；B 先于 C。</p><p>没有规定 A、B 的先后。</p></div><button className="text-action" onClick={openEvidence}>核对来源 <Arrow /></button></aside>
              <section className="work-preview"><div className="column-label">02 / 体验预览</div><h2>理清先后</h2><p className="work-instruction">用拖拽或按钮调整，看看哪几种顺序都成立。</p><SortTrial reduce={reduce} /></section>
              <aside className="work-run"><div className="column-label">03 / 制作记录</div><h2>一步一步来。</h2><ol><li><span>✓</span>材料解析<small>样例已完成</small></li><li><span>—</span>核对来源<small>样例阶段，等待审核</small></li><li><span>○</span>浏览器试玩<small>未执行</small></li></ol><p className="run-foot">真实模型调用：无<br />费用：未知（演示）</p></aside></div>
            <p className="bottom-note">这是前端交互小样，未接入项目、模型和生产引擎。</p>
          </PreviewView>}
        </AnimatePresence>
      </main>
      <footer className="colophon"><span>叙境 / 海盐与纸页</span><span>动态试作 02 · React + Motion</span><a href="README.md">设计说明 ↗</a></footer>
      <AnimatePresence>{evidence && <Evidence close={closeEvidence} origin={origin} reduce={reduce} />}</AnimatePresence>
    </div>
  </MotionConfig></LazyMotion>;
}

const mount = document.getElementById('root');
if (mount) createRoot(mount).render(<App />);
