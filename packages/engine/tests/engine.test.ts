import assert from 'node:assert/strict';
import test from 'node:test';

import {
  applyAction,
  initialState,
  isCompletePermutation,
  isCompleted,
  replayState,
  satisfiesPrecedence,
  SpecError,
  type ActionResult,
  type PlayerState,
} from '../src/engine.ts';
import { workshopSpec } from './fixtures.ts';

function runTo(state: PlayerState, ...actions: Parameters<typeof applyAction>[2][]): PlayerState {
  let current = state;
  for (const action of actions) {
    const result = applyAction(workshopSpec(), current, action);
    current = result.next_state;
  }
  return current;
}

// ---- independent expectations from the material: A<C, B<C ----

test('A<C and B<C admit exactly ABC and BAC', () => {
  const precedence = [
    { before: 'A', after: 'C', claim_id: 'c1' },
    { before: 'B', after: 'C', claim_id: 'c2' },
  ];
  const valid = ['ABC', 'BAC'].filter((order) => satisfiesPrecedence(order.split(''), precedence));
  const all = ['ABC', 'ACB', 'BAC', 'BCA', 'CAB', 'CBA'].filter((order) =>
    satisfiesPrecedence(order.split(''), precedence),
  );
  assert.deepEqual(valid, ['ABC', 'BAC']);
  assert.deepEqual(all, ['ABC', 'BAC']);
  // The material never states A<B, so neither order may be invented.
  assert.ok(satisfiesPrecedence(['A', 'B', 'C'], precedence));
  assert.ok(satisfiesPrecedence(['B', 'A', 'C'], precedence));
});

test('incomplete or duplicated sequences are rejected before judging order', () => {
  const items = [
    { id: 'A', label: 'A' },
    { id: 'B', label: 'B' },
    { id: 'C', label: 'C' },
  ];
  assert.ok(isCompletePermutation(items, ['A', 'B', 'C']));
  assert.ok(!isCompletePermutation(items, ['A', 'A', 'B']));
  assert.ok(!isCompletePermutation(items, ['A', 'B']));
  assert.ok(!isCompletePermutation(items, ['A', 'B', 'C', 'D']));

  const state = workshopSpec();
  const atSequence: PlayerState = { scene_id: 'sequence_scene', flags: { clue_seen: true, choice_done: true, never: false, bonus: false, sequence_done: false } };
  void state;
  const duplicated = applyAction(workshopSpec(), atSequence, {
    kind: 'task',
    scene_id: 'sequence_scene',
    task_id: 'sequence_steps',
    order: ['A', 'A', 'B'],
  });
  assert.equal(duplicated.result_code, 'INVALID_SEQUENCE');
  assert.equal(duplicated.next_state, atSequence, 'invalid input must not change state');

  const wrong = applyAction(workshopSpec(), atSequence, {
    kind: 'task',
    scene_id: 'sequence_scene',
    task_id: 'sequence_steps',
    order: ['A', 'C', 'B'],
  });
  assert.equal(wrong.result_code, 'WRONG_ANSWER');
  assert.equal(wrong.next_state, atSequence, 'wrong answer must not change state');
});

test('initial state uses entry scene and all-false flags', () => {
  const state = initialState(workshopSpec());
  assert.equal(state.scene_id, 'entry');
  assert.deepEqual(state.flags, { clue_seen: false, choice_done: false, sequence_done: false, never: false, bonus: false });
});

test('hotspot completes once and repeated activation is idempotent', () => {
  const spec = workshopSpec();
  const first = applyAction(spec, initialState(spec), { kind: 'task', scene_id: 'entry', task_id: 'hotspot_tool' });
  assert.equal(first.result_code, 'OK');
  assert.equal(first.next_state.flags.clue_seen, true);
  const again = applyAction(spec, first.next_state, { kind: 'task', scene_id: 'entry', task_id: 'hotspot_tool' });
  assert.equal(again.result_code, 'ALREADY_COMPLETED');
  assert.deepEqual(again.next_state, first.next_state);
});

test('wrong choice keeps state and gives claim-backed feedback', () => {
  const spec = workshopSpec();
  const atChoice: PlayerState = { scene_id: 'choice_scene', flags: { clue_seen: true, choice_done: false, sequence_done: false, never: false, bonus: false } };
  const wrong = applyAction(spec, atChoice, {
    kind: 'task',
    scene_id: 'choice_scene',
    task_id: 'choice_tool',
    option_id: 'opt_wrong',
  });
  assert.equal(wrong.result_code, 'WRONG_ANSWER');
  assert.equal(wrong.next_state, atChoice);
  assert.match(wrong.feedback, /不用于切割/);
  const right = applyAction(spec, atChoice, {
    kind: 'task',
    scene_id: 'choice_scene',
    task_id: 'choice_tool',
    option_id: 'opt_right',
  });
  assert.equal(right.result_code, 'OK');
  assert.equal(right.next_state.flags.choice_done, true);
  assert.equal(right.next_state.flags.bonus, true, 'correct option effects apply');
});

test('transition requires its condition and a navigation never sets a task flag', () => {
  const spec = workshopSpec();
  const blocked = applyAction(spec, initialState(spec), { kind: 'transition', scene_id: 'entry', transition_id: 'go_choice' });
  assert.equal(blocked.result_code, 'NOT_AVAILABLE');
  assert.equal(blocked.next_state.scene_id, 'entry');

  const afterHotspot = applyAction(spec, initialState(spec), { kind: 'task', scene_id: 'entry', task_id: 'hotspot_tool' });
  const moved = applyAction(spec, afterHotspot.next_state, { kind: 'transition', scene_id: 'entry', transition_id: 'go_choice' });
  assert.equal(moved.result_code, 'OK');
  assert.equal(moved.next_state.scene_id, 'choice_scene');
  assert.equal(moved.transition_id, 'go_choice');
  assert.equal(moved.next_state.flags.choice_done, false, 'navigation must not complete tasks');
});

test('full path completes only when every required flag is set', () => {
  const spec = workshopSpec();
  const state = runTo(
    initialState(spec),
    { kind: 'task', scene_id: 'entry', task_id: 'hotspot_tool' },
    { kind: 'transition', scene_id: 'entry', transition_id: 'go_choice' },
    { kind: 'task', scene_id: 'choice_scene', task_id: 'choice_tool', option_id: 'opt_right' },
    { kind: 'transition', scene_id: 'choice_scene', transition_id: 'go_sequence' },
    { kind: 'task', scene_id: 'sequence_scene', task_id: 'sequence_steps', order: ['B', 'A', 'C'] },
    { kind: 'transition', scene_id: 'sequence_scene', transition_id: 'finish' },
  );
  assert.equal(state.scene_id, 'done');
  assert.ok(isCompleted(spec, state));
});

test('jumping into the completion scene without all flags is refused entirely', () => {
  const spec = workshopSpec();
  const almost: PlayerState = {
    scene_id: 'sequence_scene',
    flags: { clue_seen: true, choice_done: true, sequence_done: false, never: false, bonus: false },
  };
  const result = applyAction(spec, almost, { kind: 'transition', scene_id: 'sequence_scene', transition_id: 'finish' });
  assert.equal(result.result_code, 'NOT_AVAILABLE');
  assert.equal(result.next_state, almost);
});

test('invalid actions never mutate state', () => {
  const spec = workshopSpec();
  const state = initialState(spec);
  const cases: ActionResult[] = [
    applyAction(spec, state, { kind: 'task', scene_id: 'choice_scene', task_id: 'hotspot_tool' }),
    applyAction(spec, state, { kind: 'task', scene_id: 'entry', task_id: 'missing_task' }),
    applyAction(spec, state, { kind: 'transition', scene_id: 'entry', transition_id: 'missing_transition' }),
    applyAction(spec, state, { kind: 'task', scene_id: 'entry', task_id: 'hotspot_tool', option_id: 'x' }),
  ];
  for (const result of cases) {
    assert.equal(result.result_code, 'INVALID_ACTION');
    assert.equal(result.next_state, state);
  }
});

test('replay rebuilds the entry state', () => {
  const spec = workshopSpec();
  const played = runTo(
    initialState(spec),
    { kind: 'task', scene_id: 'entry', task_id: 'hotspot_tool' },
    { kind: 'transition', scene_id: 'entry', transition_id: 'go_choice' },
  );
  const replayed = replayState(spec);
  assert.equal(replayed.scene_id, 'entry');
  assert.equal(replayed.flags.clue_seen, false);
  assert.notDeepEqual(replayed, played);
});

test('unknown runtime is refused before any action runs', () => {
  const spec = workshopSpec();
  const broken = { ...spec, runtime_version: '2.0.0' as unknown as '1.0.0' };
  assert.throws(() => initialState(broken), (error: unknown) => error instanceof SpecError && error.code === 'RUNTIME_UNSUPPORTED');
});

test('conditions referencing undeclared flags are rejected', () => {
  const spec = workshopSpec();
  const state = initialState(spec);
  const broken = {
    ...spec,
    scenes: spec.scenes.map((scene) =>
      scene.id !== 'entry'
        ? scene
        : {
            ...scene,
            transitions: [],
            tasks: scene.tasks.map((task) => ({
              ...task,
              requires: { flag_equals: { id: 'not_declared', value: false } } as const,
            })),
          },
    ),
  };
  assert.throws(
    () => applyAction(broken, state, { kind: 'task', scene_id: 'entry', task_id: 'hotspot_tool' }),
    (error: unknown) => error instanceof SpecError && error.code === 'UNKNOWN_FLAG',
  );
});
