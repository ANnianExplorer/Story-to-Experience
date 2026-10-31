import assert from 'node:assert/strict';
import test from 'node:test';

import { finalMessageFromTurn, ApiError, XujingClient } from '../src/lib/api.ts';
import { formatCost, gates, initialState, reduce, type WorkbenchState } from '../src/lib/workbench-state.ts';

function stateWith(overrides: Partial<WorkbenchState>): WorkbenchState {
  return { ...initialState, ...overrides };
}

test('a failed turn never yields a finished message from partial text', () => {
  const result = {
    turn_id: 't1',
    status: 'cancelled',
    final_text: null,
    answerability: null,
    citations: [],
    suggested_actions: [],
    cost_status: 'unknown',
    events: [{ sequence: 1, type: 'text_delta', payload: { text: '这是一段被截断' } }],
  };
  assert.equal(finalMessageFromTurn(result), null);
});

test('only a succeeded turn with a completed event is shown as an answer', () => {
  const result = {
    turn_id: 't1',
    status: 'succeeded',
    final_text: '依据材料，A 在 C 之前。',
    answerability: 'answered',
    citations: [{ span_id: 's1', source_id: 'src1', label: '材料一', quote: 'A 先于 C', claim_ids: ['c1'] }],
    suggested_actions: [],
    cost_status: 'unknown',
    events: [
      { sequence: 1, type: 'text_delta', payload: { text: '依据' } },
      { sequence: 2, type: 'citation', payload: {} },
      { sequence: 3, type: 'completed', payload: {} },
    ],
  };
  const message = finalMessageFromTurn(result);
  assert.ok(message);
  assert.equal(message.citations.length, 1);
  assert.equal(message.answerability, 'answered');
});

test('succeeded without a completed event is treated as incomplete', () => {
  const result = {
    turn_id: 't2',
    status: 'succeeded',
    final_text: '文本',
    answerability: 'answered',
    citations: [],
    suggested_actions: [],
    cost_status: 'unknown',
    events: [{ sequence: 1, type: 'text_delta', payload: { text: '文本' } }],
  };
  assert.equal(finalMessageFromTurn(result), null);
});

test('generation stays blocked until evidence is frozen', () => {
  const withoutEvidence = stateWith({ sourceId: 'src' });
  assert.equal(gates(withoutEvidence).canFreeze, false);
  assert.ok(gates(withoutEvidence).reasons.includes('至少需要一条绑定证据的事实'));

  const withClaim = stateWith({
    sourceId: 'src',
    claims: [{ id: 'c1', revision: 1, statement: '事实', content_type: 'supported', evidence_span_ids: ['s1'] }],
  });
  assert.equal(gates(withClaim).canFreeze, true);
  assert.equal(gates(withClaim).canGenerate, false);

  const frozen = reduce(withClaim, { type: 'snapshot_created', snapshotId: 'snap' });
  assert.equal(frozen.stage, 'snapshot_ready');
  assert.equal(gates(frozen).canGenerate, true);
});

test('a failed run is not reported as a candidate', () => {
  let state = stateWith({
    stage: 'generating',
    sourceId: 'src',
    snapshotId: 'snap',
    claims: [{ id: 'c1', revision: 1, statement: '事实', content_type: 'supported', evidence_span_ids: ['s1'] }],
  });
  state = reduce(state, {
    type: 'run_updated',
    run: { id: 'r1', status: 'failed', stage: 'assemble', attempt: 1, last_sequence: 3, budget: { max_calls: 12, calls_reserved: 0, calls_settled: 5, repair_rounds: 2 }, error_code: 'VALIDATION_FAILED' },
  });
  assert.equal(state.runOutcome, 'failed');
  assert.equal(state.stage, 'generating', 'stage only advances when a candidate really exists');
  // A terminal failure is not an in-flight run, so a retry is allowed.
  assert.equal(gates(state).canGenerate, true);
});

test('budget display never rounds an unknown state into success', () => {
  assert.equal(formatCost(undefined), '—');
  assert.equal(formatCost({ max_calls: 12, calls_reserved: 0, calls_settled: 7, repair_rounds: 1 }), '7/12 次调用 · 修复 1/2 轮');
});

test('API errors map to a stable code the UI can branch on', async () => {
  const fetchImpl = (async () =>
    new Response(JSON.stringify({ error: { code: 'VERSION_CONFLICT', message: '基准版本已变化。', retryable: false } }), {
      status: 409,
      headers: { 'content-type': 'application/json' },
    })) as unknown as typeof fetch;
  const client = new XujingClient({ fetchImpl });
  await assert.rejects(
    () => client.getProject('p1'),
    (error: unknown) => error instanceof ApiError && error.code === 'VERSION_CONFLICT' && error.status === 409,
  );
});

test('an unparsable response is an error, not an empty success', async () => {
  const fetchImpl = (async () => new Response('<html>gateway error</html>', { status: 502 })) as unknown as typeof fetch;
  const client = new XujingClient({ fetchImpl });
  await assert.rejects(
    () => client.listProjects(),
    (error: unknown) => error instanceof ApiError && error.code === 'INVALID_RESPONSE',
  );
});

test('requests send the idempotency key and never a provider credential', async () => {
  const calls: { url: string; init: RequestInit }[] = [];
  const fetchImpl = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response(JSON.stringify({ data: { run_id: 'r1', created: true } }), {
      status: 202,
      headers: { 'content-type': 'application/json' },
    });
  }) as unknown as typeof fetch;
  const client = new XujingClient({ fetchImpl, actorId: 'actor-1' });
  const result = await client.submitRun(
    'p1',
    { snapshotId: 'snap', briefRevision: 1, instruction: '保留出处', autoContinue: true },
    'idem-1',
  );
  assert.equal(result.run_id, 'r1');
  const headers = calls[0]!.init.headers as Record<string, string>;
  assert.equal(headers['Idempotency-Key'], 'idem-1');
  assert.equal(headers['x-actor-id'], 'actor-1');
  assert.ok(!JSON.stringify(headers).toLowerCase().includes('authorization'));
});

test('router maps hashes to typed routes and round-trips', async () => {
  const { parseRoute, routeToHash } = await import('../src/lib/router.ts');
  assert.deepEqual(parseRoute(''), { name: 'projects' });
  assert.deepEqual(parseRoute('#/'), { name: 'projects' });
  assert.deepEqual(parseRoute('#/projects/abc-123'), { name: 'project', projectId: 'abc-123' });
  assert.deepEqual(parseRoute('#/projects/%E4%B8%AD%E6%96%87'), { name: 'project', projectId: '中文' });
  assert.deepEqual(parseRoute('#/nope/x'), { name: 'notFound', path: '/nope/x' });
  assert.equal(routeToHash({ name: 'project', projectId: 'abc' }), '#/projects/abc');
  assert.equal(routeToHash({ name: 'projects' }), '#/');
});
