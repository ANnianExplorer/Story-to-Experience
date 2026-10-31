import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import { workshopSpec } from '../../engine/tests/fixtures.ts';
import { allPermutations, searchStates, validate, CHECKER_VERSION } from '../src/validator.ts';
import type { ExperienceSpecModel } from '../../engine/src/engine.ts';

const EVIDENCE = [
  '30000000-0000-4000-8000-000000000001',
  '30000000-0000-4000-8000-000000000002',
  '30000000-0000-4000-8000-000000000003',
];
const HASHES = { specHash: 'a'.repeat(64), semanticHash: 'b'.repeat(64) };

function specWith(mutate: (spec: ExperienceSpecModel) => void): ExperienceSpecModel {
  const spec = workshopSpec();
  mutate(spec);
  return spec;
}

test('valid fixture passes every layer and yields a replayable path', () => {
  const report = validate(workshopSpec(), EVIDENCE, HASHES);
  assert.equal(report.status, 'passed');
  assert.deepEqual(report.layers, { structure: 'passed', semantics: 'passed', state: 'passed' });
  assert.equal(report.checker_version, CHECKER_VERSION);
  assert.ok(report.search.terminal_reachable);
  assert.ok(report.search.witness && report.search.witness.length >= 4);
  assert.equal(report.playtest_paths.length, 1);
});

test('missing completion flag in completion list fails structure', () => {
  const report = validate(
    specWith((spec) => {
      spec.completion.required_flags = ['clue_seen', 'choice_done'];
    }),
    EVIDENCE,
    HASHES,
  );
  assert.equal(report.status, 'failed');
  assert.ok(report.findings.some((item) => item.code === 'COMPLETION_MISMATCH'));
});

test('unknown references are reported per layer', () => {
  const report = validate(
    specWith((spec) => {
      spec.scenes[1]!.transitions[0]!.target_scene = 'ghost';
      spec.objectives[0]!.claim_ids = ['missing_claim'];
      spec.scenes[0]!.tasks[0]!.completion_flag = 'not_declared';
    }),
    EVIDENCE,
    HASHES,
  );
  assert.equal(report.status, 'failed');
  const codes = report.findings.map((item) => item.code);
  assert.ok(codes.includes('UNKNOWN_SCENE'));
  assert.ok(codes.includes('UNKNOWN_CLAIM'));
  assert.ok(codes.includes('UNKNOWN_FLAG'));
});

test('required task without evidence-backed claim is rejected (F03-AT01)', () => {
  const report = validate(
    specWith((spec) => {
      const task = spec.scenes[0]!.tasks[0]!;
      task.claim_ids = ['legend_only'];
      spec.claims.push({
        id: 'legend_only',
        statement: '合成传说。',
        content_type: 'adaptation',
        evidence_span_ids: [],
        source_claim_id: '20000000-0000-4000-8000-000000000009',
        source_claim_revision: 1,
      });
    }),
    EVIDENCE,
    HASHES,
  );
  assert.ok(report.findings.some((item) => item.code === 'REQUIRED_TASK_WITHOUT_SUPPORT'));
});

test('invented A<B precedence is caught as unsolvable only when it contradicts the graph', () => {
  // A<B together with B<A is a cycle => unsolvable.
  const report = validate(
    specWith((spec) => {
      const task = spec.scenes[2]!.tasks[0]!;
      if (task.type !== 'sequence') throw new Error('fixture changed');
      task.precedence.push({ before: 'C', after: 'A', claim_id: 'claim_A_C' });
    }),
    EVIDENCE,
    HASHES,
  );
  assert.ok(report.findings.some((item) => item.code === 'SEQUENCE_CYCLE'));
  assert.equal(report.status, 'failed');
});

test('dead end is a failed state search, not inconclusive', () => {
  const report = validate(
    specWith((spec) => {
      // Completion needs sequence_done but the only task setting it is unreachable.
      spec.scenes[2]!.tasks[0]!.requires = { flag_equals: { id: 'never', value: true } };
    }),
    EVIDENCE,
    HASHES,
  );
  assert.equal(report.status, 'failed');
  assert.equal(report.search.terminal_reachable, false);
  assert.ok(report.findings.some((item) => item.code === 'CONDITION_UNSATISFIABLE'));
});

test('budget exhaustion reports inconclusive instead of passing', () => {
  const result = searchStates(workshopSpec(), { stateLimit: 0 });
  assert.equal(result.status, 'inconclusive');
  assert.equal(result.budget_exhausted, true);
});

test('permutations of six items are all enumerated deterministically', () => {
  const permutations = allPermutations(['A', 'B', 'C', 'D', 'E', 'F']);
  assert.equal(permutations.length, 720);
  assert.deepEqual(permutations[0], ['A', 'B', 'C', 'D', 'E', 'F']);
  assert.deepEqual(permutations[719], ['F', 'E', 'D', 'C', 'B', 'A']);
});

test('stdin/stdout bridge validates a real payload without paths or code', () => {
  const script = fileURLToPath(new URL('../bin/validate.ts', import.meta.url));
  const payload = JSON.stringify({
    protocol_version: '1.0.0',
    spec: workshopSpec(),
    evidence_span_ids: EVIDENCE,
    spec_hash: HASHES.specHash,
    semantic_hash: HASHES.semanticHash,
  });
  const output = execFileSync(process.execPath, [script], { input: payload, encoding: 'utf8' });
  const parsed = JSON.parse(output) as { protocol_version: string; report: { status: string } };
  assert.equal(parsed.protocol_version, '1.0.0');
  assert.equal(parsed.report.status, 'passed');
});

test('bridge rejects a bad protocol version with a machine-readable error', () => {
  const script = fileURLToPath(new URL('../bin/validate.ts', import.meta.url));
  const payload = JSON.stringify({
    protocol_version: '0.1.0',
    spec: workshopSpec(),
    evidence_span_ids: EVIDENCE,
    spec_hash: 'a'.repeat(64),
    semantic_hash: 'b'.repeat(64),
  });
  const result = spawnSync(process.execPath, [script], { input: payload, encoding: 'utf8' });
  assert.equal(result.status, 2);
  assert.equal(JSON.parse(result.stdout).error.code, 'PROTOCOL_VERSION_UNSUPPORTED');
});
