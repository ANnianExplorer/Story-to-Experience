import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { JSDOM, VirtualConsole } from 'jsdom';

const html = await readFile(new URL('../../../docs/frontend/style-preview.html', import.meta.url), 'utf8');

async function waitFor(predicate, label, timeout = 3000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await new Promise(resolve => setTimeout(resolve, 16));
  }
  assert.fail(`Timed out: ${label}`);
}

async function openPreview(systemReduced = false) {
  const failures = [];
  const console = new VirtualConsole();
  console.on('jsdomError', error => { if (failures.length < 20) failures.push(error.message); });
  const dom = new JSDOM(html, {
    runScripts: 'dangerously', // Only the locally authored, compiled preview. No remote resources.
    pretendToBeVisual: true,
    virtualConsole: console,
    beforeParse(window) {
      window.matchMedia = query => ({ matches: query.includes('prefers-reduced-motion') && systemReduced, media: query, onchange: null, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent() { return true; } });
      window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
      window.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
      window.scrollTo = () => {};
    },
  });
  await waitFor(() => dom.window.document.querySelector('.chapter'), 'initial React render');
  return { dom, doc: dom.window.document, failures };
}

test('clue collection immediately changes chapter and opens an accessible source drawer', async () => {
  const { dom, doc, failures } = await openPreview();
  try {
    doc.querySelector('.hotspot').click();
    await waitFor(() => doc.querySelector('[aria-current="step"]')?.textContent.includes('找到依据'), 'clue commits chapter');
    assert.match(doc.querySelector('.bottom-note').textContent, /已拾取 1 条/);
    const sourceButton = Array.from(doc.querySelectorAll('button')).find(button => button.textContent.includes('翻开原文'));
    sourceButton.focus(); sourceButton.click();
    await waitFor(() => doc.querySelector('[role="dialog"]'), 'source drawer mounts');
    assert.equal(doc.querySelector('[role="dialog"]').getAttribute('aria-modal'), 'true');
    assert.match(doc.querySelector('blockquote').textContent, /未规定 A 与 B/);
    assert.equal(doc.activeElement.getAttribute('aria-label'), '关闭来源');
    doc.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true }));
    assert.match(doc.activeElement.textContent, /回到刚才/);
    doc.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
    assert.equal(doc.activeElement.getAttribute('aria-label'), '关闭来源');
    doc.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await waitFor(() => !doc.querySelector('[role="dialog"]'), 'Escape closes source drawer');
    await waitFor(() => doc.activeElement === sourceButton, 'focus returns to source trigger after exit cleanup');
    assert.equal(doc.body.style.overflow, '', 'scroll lock cleaned up');
    assert.deepEqual(failures, []);
  } finally { dom.window.close(); }
});

test('sort feedback rejects CAB and accepts both ABC and BAC with button controls', async () => {
  const { dom, doc, failures } = await openPreview(true);
  try {
    Array.from(doc.querySelectorAll('.chapter')).at(2).click();
    await waitFor(() => doc.querySelector('.sort-list'), 'sorting chapter');
    const order = () => Array.from(doc.querySelectorAll('.piece-letter')).map(node => node.textContent).join('');
    const submit = () => doc.querySelector('.sort-bottom button').click();
    assert.equal(order(), 'CAB');
    submit(); await waitFor(() => doc.querySelector('.sort-message.invalid'), 'invalid order feedback');
    assert.match(doc.querySelector('.sort-message').textContent, /都要在 C 前/);
    doc.querySelector('[aria-label="上移步骤 A"]').click();
    await waitFor(() => order() === 'ACB', 'move A');
    doc.querySelector('[aria-label="上移步骤 B"]').click();
    await waitFor(() => order() === 'ABC', 'move B');
    submit(); await waitFor(() => doc.querySelector('.sort-message.valid'), 'ABC valid');
    doc.querySelector('[aria-label="上移步骤 B"]').click();
    await waitFor(() => order() === 'BAC', 'swap free A/B order');
    submit(); await waitFor(() => doc.querySelector('.sort-message.valid'), 'BAC valid');
    assert.deepEqual(failures, []);
  } finally { dom.window.close(); }
});

test('local reduced-motion control changes the entire preview and keeps view switching usable', async () => {
  const { dom, doc, failures } = await openPreview();
  try {
    doc.querySelector('.motion-toggle').click();
    await waitFor(() => doc.querySelector('.paper-app').dataset.motion === 'reduce', 'local reduced motion');
    assert.equal(doc.querySelector('.motion-toggle').getAttribute('aria-pressed'), 'true');
    const work = Array.from(doc.querySelectorAll('nav button')).find(button => button.textContent.includes('创作工作台'));
    work.click();
    await waitFor(() => doc.querySelector('.workbench'), 'workbench view');
    assert.match(doc.querySelector('.work-run').textContent, /真实模型调用：无/);
    assert.ok(doc.querySelector('.sort-list'), 'workbench includes usable interaction');
    assert.deepEqual(failures, []);
  } finally { dom.window.close(); }
});

test('drag handlers move an existing piece but ignore a foreign drop', async () => {
  const { dom, doc, failures } = await openPreview();
  try {
    Array.from(doc.querySelectorAll('.chapter')).at(2).click();
    await waitFor(() => doc.querySelector('.sort-list'), 'sorting chapter');
    const order = () => Array.from(doc.querySelectorAll('.piece-letter')).map(node => node.textContent).join('');
    const pieces = () => Array.from(doc.querySelectorAll('.sort-piece'));
    const data = new Map();
    const transfer = { effectAllowed: 'none', setData(key, value) { data.set(key, value); }, getData(key) { return data.get(key); } };
    const dispatch = (target, type) => {
      const event = new dom.window.Event(type, { bubbles: true, cancelable: true });
      Object.defineProperty(event, 'dataTransfer', { value: transfer });
      target.dispatchEvent(event); return event;
    };
    dispatch(pieces()[2], 'drop');
    assert.equal(order(), 'CAB', 'foreign drop must not invent a dragged piece');
    dispatch(pieces()[0], 'dragstart');
    assert.equal(data.get('text/plain'), 'C');
    assert.equal(dispatch(pieces()[2], 'dragover').defaultPrevented, true);
    dispatch(pieces()[2], 'drop');
    await waitFor(() => order() === 'ABC', 'drop commits new order without waiting for animation');
    assert.deepEqual(failures, []);
  } finally { dom.window.close(); }
});

test('OS reduced-motion setting cannot be overridden and initial title is visible', async () => {
  const { dom, doc, failures } = await openPreview(true);
  try {
    assert.equal(doc.querySelector('.paper-app').dataset.motion, 'reduce');
    assert.equal(doc.querySelector('.motion-toggle').disabled, true);
    for (const part of doc.querySelectorAll('.title-mask > span')) {
      assert.notEqual(part.style.opacity, '0');
      assert.notEqual(part.style.clipPath, 'inset(0 0 100% 0)');
    }
    doc.querySelector('.hotspot').click();
    await waitFor(() => doc.querySelector('.evidence-slip'), 'clue remains usable without animation');
    assert.deepEqual(failures, []);
  } finally { dom.window.close(); }
});
