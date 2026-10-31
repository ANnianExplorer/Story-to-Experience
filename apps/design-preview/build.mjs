import { build } from 'esbuild';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve, dirname } from 'node:path';
import { gzipSync } from 'node:zlib';

const here = dirname(fileURLToPath(import.meta.url));
const result = await build({
  absWorkingDir: here,
  entryPoints: ['src/main.tsx'],
  bundle: true, write: false, minify: true,
  format: 'iife', target: ['es2020'], outfile: 'out/preview.js',
  define: { 'process.env.NODE_ENV': '"production"' },
  legalComments: 'inline', metafile: true,
});
const js = result.outputFiles.find(file => file.path.endsWith('.js'))?.text;
const css = result.outputFiles.find(file => file.path.endsWith('.css'))?.text;
if (!js || !css) throw new Error('Preview build did not produce both JavaScript and CSS.');
const escapedScript = js.replace(/<\/script/gi, '<\\/script');
const licenseNames = ['react', 'react-dom', 'scheduler', 'motion', 'framer-motion', 'motion-dom', 'motion-utils', 'tslib'];
const notices = [];
for (const name of licenseNames) {
  let license;
  for (const filename of ['LICENSE', 'LICENSE.md', 'LICENSE.txt', 'CopyrightNotice.txt']) {
    try { license = await readFile(resolve(here, 'node_modules', name, filename), 'utf8'); break; }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  if (!license) throw new Error(`Missing bundled dependency license: ${name}`);
  notices.push(`${name}\n${license}`);
}
const licenseComment = notices.join('\n\n').replace(/--/g, '—');
const html = `<!doctype html>
<!-- Bundled third-party notices\n${licenseComment}\n-->
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>叙境 · 动态试作 02</title><style>${css}</style></head><body><div id="root"><p style="padding:32px">正在打开叙境动态小样……</p></div><noscript>此动态预览需要启用 JavaScript。设计说明位于同目录 README.md。</noscript><script>${escapedScript}</script></body></html>
`;
const destination = resolve(here, '../../docs/frontend/style-preview.html');
if (process.argv.includes('--check')) {
  if (await readFile(destination, 'utf8') !== html) throw new Error('Preview is stale. Run npm run build in apps/design-preview.');
} else {
  await writeFile(destination, html, 'utf8');
}
const baseline = await build({
  absWorkingDir: here,
  stdin: { contents: 'import React from "react";import {createRoot} from "react-dom/client";createRoot(document.getElementById("root")).render(React.createElement("div",null,"preview"));', resolveDir: here, loader: 'js' },
  bundle: true, write: false, minify: true, format: 'iife', target: ['es2020'],
  define: { 'process.env.NODE_ENV': '"production"' }, legalComments: 'inline',
});
const fullGzip = gzipSync(js).length;
const baselineGzip = gzipSync(baseline.outputFiles[0].contents).length;
console.log(JSON.stringify({ output: destination, standaloneBytes: Buffer.byteLength(html), jsGzipBytes: fullGzip, reactBaselineGzipBytes: baselineGzip, incrementalJsUpperEstimateBytes: fullGzip - baselineGzip, scope: 'Standalone React/Motion visual prototype; not a production player or measured browser performance.' }, null, 2));
