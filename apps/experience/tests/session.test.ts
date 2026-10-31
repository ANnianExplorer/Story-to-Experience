import assert from 'node:assert/strict';
import test from 'node:test';

import { applyAction, initialState, isCompleted, type ExperienceSpecModel } from '../../../packages/engine/src/engine.ts';
import { guideAnswer, PlayerClient, PlayerError, type GuideTurnResult } from '../src/lib/player-api.ts';
import { currentScene, hintFor, openSession, reduceSession, sessionCompleted } from '../src/lib/session.ts';

function spec(): ExperienceSpecModel {
  return {
    schema_version: '1.0.0',
    runtime_version: '1.0.0',
    brief: { audience: '五年级', duration_minutes: 5, learning_goals: ['观察'] },
    source_snapshot_id: '10000000-0000-4000-8000-000000000001',
    entry_scene: 'entry',
    flags: [{ id: 'seen', initial: false }, { id: 'never', initial: false }],
    claims: [
      {
        id: 'claim_1',
        statement: '工具用于观察。',
        content_type: 'supported',
        evidence_span_ids: ['30000000-0000-4000-8000-000000000001'],
        source_claim_id: '20000000-0000-4000-8000-000000000001',
        source_claim_revision: 1,
      },
    ],
    objectives: [{ id: 'obj', description: '辨认工具', claim_ids: ['claim_1'] }],
    scenes: [
      {
        id: 'entry',
        title: '入口',
        text: '观察工具。',
        content_type: 'supported',
        asset_ids: [],
        claim_ids: ['claim_1'],
        tasks: [
          {
            id: 'hotspot',
            type: 'hotspot',
            label: '观察',
            required: true,
            completion_flag: 'seen',
            objective_ids: ['obj'],
            claim_ids: ['claim_1'],
            requires: { flag_equals: { id: 'never', value: false } },
            on_success: [],
            feedback: { success: '看到了。', failure: '再找找。', claim_ids: ['claim_1'] },
            hints: ['看左侧。', '再看右边。'],
          },
        ],
        transitions: [
          {
            id: 'go_done',
            label: '完成',
            requires: { flag_equals: { id: 'seen', value: true } },
            target_scene: 'done',
          },
        ],
      },
      {
        id: 'done',
        title: '完成',
        text: '结束。',
        content_type: 'adaptation',
        asset_ids: [],
        claim_ids: [],
        tasks: [],
        transitions: [],
      },
    ],
    completion: { scene_id: 'done', required_flags: ['seen'] },
    asset_manifest: [],
  };
}

test('a locked transition is refused and state is unchanged', () => {
  const session = openSession(spec(), 'exp-1', null);
  const next = reduceSession(session, {
    type: 'action',
    input: { kind: 'transition', scene_id: 'entry', transition_id: 'go_done' },
  });
  assert.equal(next.state.scene_id, 'entry');
  assert.equal(next.lastFeedback?.code, 'NOT_AVAILABLE');
});

test('playing through completes and replay restores the entry state', () => {
  let session = openSession(spec(), 'exp-1', null);
  session = reduceSession(session, { type: 'action', input: { kind: 'task', scene_id: 'entry', task_id: 'hotspot' } });
  session = reduceSession(session, { type: 'action', input: { kind: 'transition', scene_id: 'entry', transition_id: 'go_done' } });
  assert.ok(sessionCompleted(session));
  const replayed = reduceSession(session, { type: 'replay' });
  assert.equal(replayed.state.scene_id, 'entry');
  assert.equal(replayed.state.flags.seen, false);
});

test('hints advance one level at a time and never unlock tasks', () => {
  let session = openSession(spec(), 'exp-1', null);
  assert.equal(hintFor(session), '看左侧。');
  session = reduceSession(session, { type: 'hint', level: 3 });
  assert.equal(hintFor(session), '再看右边。');
  assert.equal(session.state.flags.seen, false, 'a hint must not change logical state');
});

test('current scene resolves from the engine state', () => {
  const session = openSession(spec(), 'exp-1', null);
  assert.equal(currentScene(session)?.id, 'entry');
});

test('a canceled guide turn never renders partial text as an answer', () => {
  const result: GuideTurnResult = {
    turn_id: 't1',
    status: 'cancelled',
    final_text: null,
    answerability: null,
    citations: [],
    suggested_actions: [],
    cost_status: 'unknown',
    events: [{ sequence: 1, type: 'text_delta', payload: { text: '半句' } }],
  };
  assert.equal(guideAnswer(result), null);
});

test('a completed guide turn returns its citations', () => {
  const result: GuideTurnResult = {
    turn_id: 't2',
    status: 'succeeded',
    final_text: '材料写到工具用于观察。',
    answerability: 'answered',
    citations: [{ span_id: 's1', source_id: 'src', label: '材料', quote: '工具用于观察。', claim_ids: ['claim_1'] }],
    suggested_actions: [],
    cost_status: 'unknown',
    events: [{ sequence: 1, type: 'completed', payload: {} }],
  };
  const answer = guideAnswer(result);
  assert.ok(answer);
  assert.equal(answer.citations.length, 1);
});

test('a revoked share surfaces as a typed error, not an empty experience', async () => {
  const fetchImpl = (async () =>
    new Response(JSON.stringify({ error: { code: 'SHARE_NOT_FOUND', message: '分享不存在或已失效。' } }), {
      status: 404,
      headers: { 'content-type': 'application/json' },
    })) as unknown as typeof fetch;
  const client = new PlayerClient({ fetchImpl });
  await assert.rejects(
    () => client.manifest('dead-token'),
    (error: unknown) => error instanceof PlayerError && error.code === 'SHARE_NOT_FOUND',
  );
});

test('the player never sends credentials or project-management paths', async () => {
  const calls: { url: string; init: RequestInit }[] = [];
  const fetchImpl = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response(JSON.stringify({ data: { session_id: 's', version_id: 'v', expires_at: null } }), {
      status: 201,
      headers: { 'content-type': 'application/json' },
    });
  }) as unknown as typeof fetch;
  const client = new PlayerClient({ fetchImpl });
  await client.openSession('tok');
  const [call] = calls;
  assert.ok(call);
  assert.ok(call.url.startsWith('/api/v1/share/'));
  const headers = call.init.headers as Record<string, string>;
  assert.ok(!('authorization' in headers));
  assert.ok(!('x-actor-id' in headers), 'participants must not impersonate a creator');
});

test('the engine and the player agree on completion', () => {
  const model = spec();
  let state = initialState(model);
  const step = applyAction(model, state, { kind: 'task', scene_id: 'entry', task_id: 'hotspot' });
  state = step.next_state;
  const jump = applyAction(model, state, { kind: 'transition', scene_id: 'entry', transition_id: 'go_done' });
  assert.ok(isCompleted(model, jump.next_state));
});
