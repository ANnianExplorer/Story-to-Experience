import { compile } from 'json-schema-to-typescript';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const check = process.argv.includes('--check');

/** Schemas whose TypeScript types are derived; names become exported types. */
const targets = [
  { schema: 'experience-spec.schema.json', out: 'generated/experience-spec.ts', name: 'ExperienceSpec' },
  { schema: 'agent-protocol.schema.json', out: 'generated/agent-protocol.ts', name: 'AgentProtocol' },
  { schema: 'dialogue-profile.schema.json', out: 'generated/dialogue-profile.ts', name: 'DialogueProfile' },
];

/**
 * Large ``maxItems`` bounds would otherwise expand into hundreds of tuple
 * variants in the emitted types. Above this width the generated type falls back
 * to ``T[]``; the JSON Schema (and therefore runtime validation) keeps the real
 * bound. Small arrays keep exact tuple types because they are readable.
 */
const TUPLE_LIMIT = 4;

function compactArrays(node) {
  if (Array.isArray(node)) return node.map(compactArrays);
  if (node === null || typeof node !== 'object') return node;
  const copy = {};
  for (const [key, value] of Object.entries(node)) copy[key] = compactArrays(value);
  const width = Math.max(typeof copy.minItems === 'number' ? copy.minItems : 0, typeof copy.maxItems === 'number' ? copy.maxItems : 0);
  if (width > TUPLE_LIMIT) {
    delete copy.minItems;
    delete copy.maxItems;
  }
  return copy;
}

for (const target of targets) {
  const source = JSON.parse(await readFile(resolve(root, target.schema), 'utf8'));
  const banner = `/* Generated from packages/contracts/${target.schema} — do not edit by hand. */\n`;
  const code = banner + (await compile(compactArrays(source), target.name, {
    bannerComment: '',
    additionalProperties: false,
    style: { singleQuote: true, semi: true, tabWidth: 2, printWidth: 120 },
  }));
  const destination = resolve(root, target.out);
  if (check) {
    const current = await readFile(destination, 'utf8').catch(() => null);
    if (current !== code) {
      console.error(`Generated type is stale: ${target.out}\nRun: npm run generate (in packages/contracts)`);
      process.exitCode = 1;
    }
  } else {
    await mkdir(dirname(destination), { recursive: true });
    await writeFile(destination, code, 'utf8');
  }
}

if (!check) console.log('generated contract types written');
else if (process.exitCode !== 1) console.log('generated contract types up to date');
