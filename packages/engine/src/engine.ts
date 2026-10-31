/**
 * Deterministic experience engine (ADR-0004).
 *
 * Pure functions only: no I/O, no clock, no randomness, no DOM, no model calls.
 * The player and the validator share this implementation so a reachability
 * proof cannot drift from real play behaviour.
 */
export const SUPPORTED_RUNTIME = '1.0.0' as const;
export const SUPPORTED_SCHEMA = '1.0.0' as const;

export type Condition =
  | { all: Condition[] }
  | { any: Condition[] }
  | { not: Condition }
  | { flag_equals: { id: string; value: boolean } };

export type Effect = { set_flag: string; value: true };

export type TaskType = 'hotspot' | 'choice' | 'sequence';
export type ContentType = 'supported' | 'legend' | 'adaptation' | 'unconfirmed';

export interface TaskBase {
  id: string;
  type: TaskType;
  label: string;
  required: boolean;
  completion_flag: string;
  objective_ids: string[];
  claim_ids: string[];
  requires: Condition;
  on_success: Effect[];
  feedback: { success: string; failure: string; claim_ids: string[] };
  hints: string[];
}

export interface Hotspot extends TaskBase {
  type: 'hotspot';
}

export interface ChoiceOption {
  id: string;
  label: string;
  correct: boolean;
  feedback: string;
  on_success: Effect[];
  target_scene?: string;
}

export interface Choice extends TaskBase {
  type: 'choice';
  options: ChoiceOption[];
}

export interface SequenceItem {
  id: string;
  label: string;
}

export interface Precedence {
  before: string;
  after: string;
  claim_id: string;
}

export interface Sequence extends TaskBase {
  type: 'sequence';
  items: SequenceItem[];
  precedence: Precedence[];
}

export type Task = Hotspot | Choice | Sequence;

export interface Transition {
  id: string;
  label: string;
  requires: Condition;
  target_scene: string;
}

export interface Scene {
  id: string;
  title: string;
  text: string;
  content_type: ContentType;
  asset_ids: string[];
  tasks: Task[];
  transitions: Transition[];
  claim_ids: string[];
}

export interface ClaimModel {
  id: string;
  statement: string;
  content_type: ContentType;
  evidence_span_ids: string[];
  source_claim_id: string;
  source_claim_revision: number;
}

/** Runtime model. Structurally compatible with the generated ExperienceSpec type. */
export interface ExperienceSpecModel {
  schema_version: '1.0.0';
  runtime_version: '1.0.0';
  brief: { audience: string; duration_minutes: number; learning_goals: string[] };
  source_snapshot_id: string;
  entry_scene: string;
  flags: { id: string; initial: false }[];
  claims: ClaimModel[];
  objectives: { id: string; description: string; claim_ids: string[] }[];
  scenes: Scene[];
  completion: { scene_id: string; required_flags: string[] };
  asset_manifest: {
    id: string;
    sha256: string;
    mime_type: 'image/png' | 'image/jpeg' | 'image/webp';
    license_note: string;
  }[];
}

export interface PlayerState {
  scene_id: string;
  flags: Readonly<Record<string, boolean>>;
}

export type ResultCode =
  | 'OK'
  | 'WRONG_ANSWER'
  | 'ALREADY_COMPLETED'
  | 'NOT_AVAILABLE'
  | 'INVALID_ACTION'
  | 'INVALID_SEQUENCE'
  | 'INCOMPLETE_REQUIREMENTS';

export interface ActionResult {
  result_code: ResultCode;
  next_state: PlayerState;
  feedback: string;
  completed: boolean;
  /** Scene the action was issued in (differs from next_state.scene_id on a jump). */
  scene_id: string;
  task_id: string | null;
  transition_id: string | null;
}

export type ActionInput =
  | { kind: 'task'; scene_id: string; task_id: string; option_id?: string; order?: string[] }
  | { kind: 'transition'; scene_id: string; transition_id: string };

export class SpecError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'SpecError';
    this.code = code;
  }
}

function specError(code: string, message: string): never {
  throw new SpecError(code, message);
}

export function assertSupportedRuntime(spec: ExperienceSpecModel): void {
  if (spec.runtime_version !== SUPPORTED_RUNTIME) {
    specError('RUNTIME_UNSUPPORTED', `不支持的运行时版本：${String(spec.runtime_version)}`);
  }
  if (spec.schema_version !== SUPPORTED_SCHEMA) {
    specError('SCHEMA_UNSUPPORTED', `不支持的规格版本：${String(spec.schema_version)}`);
  }
}

export function initialState(spec: ExperienceSpecModel): PlayerState {
  assertSupportedRuntime(spec);
  const flags: Record<string, boolean> = {};
  for (const flag of spec.flags) flags[flag.id] = false;
  return Object.freeze({ scene_id: spec.entry_scene, flags: Object.freeze(flags) }) as PlayerState;
}

export function evaluateCondition(spec: ExperienceSpecModel, state: PlayerState, condition: Condition): boolean {
  if ('all' in condition) return condition.all.every((child) => evaluateCondition(spec, state, child));
  if ('any' in condition) return condition.any.some((child) => evaluateCondition(spec, state, child));
  if ('not' in condition) return !evaluateCondition(spec, state, condition.not);
  if ('flag_equals' in condition) {
    const { id, value } = condition.flag_equals;
    if (!(id in state.flags)) specError('UNKNOWN_FLAG', `条件引用了未声明的标记：${id}`);
    return state.flags[id] === value;
  }
  return specError('INVALID_CONDITION', '条件结构不受支持。');
}

export function findScene(spec: ExperienceSpecModel, sceneId: string): Scene {
  const scene = spec.scenes.find((candidate) => candidate.id === sceneId);
  if (!scene) specError('UNKNOWN_SCENE', `未知场景：${sceneId}`);
  return scene;
}

function withFlags(state: PlayerState, flagIds: readonly string[]): PlayerState {
  if (flagIds.length === 0) return state;
  const flags = { ...state.flags };
  for (const id of flagIds) {
    if (!(id in flags)) specError('UNKNOWN_FLAG', `效果引用了未声明的标记：${id}`);
    // Effects are true-only by contract: no false assignment, no toggling.
    flags[id] = true;
  }
  return Object.freeze({ scene_id: state.scene_id, flags: Object.freeze(flags) }) as PlayerState;
}

function withScene(state: PlayerState, sceneId: string): PlayerState {
  return Object.freeze({ scene_id: sceneId, flags: state.flags }) as PlayerState;
}

function applyEffects(state: PlayerState, effects: readonly Effect[]): PlayerState {
  return withFlags(
    state,
    effects.map((effect) => effect.set_flag),
  );
}

export function requiredFlagsSatisfied(spec: ExperienceSpecModel, state: PlayerState): boolean {
  return spec.completion.required_flags.every((flag) => {
    if (!(flag in state.flags)) specError('UNKNOWN_FLAG', `完成条件引用了未声明的标记：${flag}`);
    return state.flags[flag] === true;
  });
}

export function isCompleted(spec: ExperienceSpecModel, state: PlayerState): boolean {
  return state.scene_id === spec.completion.scene_id && requiredFlagsSatisfied(spec, state);
}

/** Validate that a permutation contains each declared item exactly once. */
export function isCompletePermutation(items: readonly SequenceItem[], order: readonly string[]): boolean {
  if (order.length !== items.length) return false;
  const expected = new Set(items.map((item) => item.id));
  const seen = new Set<string>();
  for (const id of order) {
    if (!expected.has(id) || seen.has(id)) return false;
    seen.add(id);
  }
  return seen.size === expected.size;
}

/** A permutation satisfies the precedence graph when every declared edge holds. */
export function satisfiesPrecedence(order: readonly string[], precedence: readonly Precedence[]): boolean {
  const position = new Map<string, number>();
  order.forEach((id, index) => position.set(id, index));
  return precedence.every((edge) => {
    const before = position.get(edge.before);
    const after = position.get(edge.after);
    if (before === undefined || after === undefined) return false;
    return before < after;
  });
}

function reject(state: PlayerState, code: ResultCode, message: string, task: Task | null): ActionResult {
  return {
    result_code: code,
    next_state: state,
    feedback: task ? task.feedback.failure : message,
    completed: false,
    scene_id: state.scene_id,
    task_id: task ? task.id : null,
    transition_id: null,
  };
}

/** A jump into the completion scene must already satisfy every required flag;
 * otherwise the whole action is refused with no partial write. */
function tryJump(spec: ExperienceSpecModel, state: PlayerState, target: string | undefined): PlayerState | null {
  if (!target) return state;
  findScene(spec, target);
  if (target === spec.completion.scene_id && !requiredFlagsSatisfied(spec, state)) return null;
  return withScene(state, target);
}

function okResult(
  spec: ExperienceSpecModel,
  next: PlayerState,
  feedback: string,
  sceneId: string,
  task: Task | null = null,
  transition: Transition | null = null,
): ActionResult {
  return {
    result_code: 'OK',
    next_state: next,
    feedback,
    completed: isCompleted(spec, next),
    scene_id: sceneId,
    task_id: task ? task.id : null,
    transition_id: transition ? transition.id : null,
  };
}

export function applyAction(spec: ExperienceSpecModel, state: PlayerState, input: ActionInput): ActionResult {
  assertSupportedRuntime(spec);
  if (input.scene_id !== state.scene_id) {
    return reject(state, 'INVALID_ACTION', '动作不属于当前场景。', null);
  }
  const scene = findScene(spec, state.scene_id);

  if (input.kind === 'transition') {
    const transition = scene.transitions.find((candidate) => candidate.id === input.transition_id);
    if (!transition) return reject(state, 'INVALID_ACTION', '未知的场景导航动作。', null);
    if (!evaluateCondition(spec, state, transition.requires)) {
      return reject(state, 'NOT_AVAILABLE', '前置条件尚未满足。', null);
    }
    const jumped = tryJump(spec, state, transition.target_scene);
    if (!jumped) return reject(state, 'INCOMPLETE_REQUIREMENTS', '完成条件尚未全部满足。', null);
    return okResult(spec, jumped, transition.label, state.scene_id, null, transition);
  }

  const task = scene.tasks.find((candidate) => candidate.id === input.task_id);
  if (!task) return reject(state, 'INVALID_ACTION', '未知任务。', null);
  if (state.flags[task.completion_flag]) {
    // Idempotent: repeated success never applies effects twice.
    return {
      result_code: 'ALREADY_COMPLETED',
      next_state: state,
      feedback: task.feedback.success,
      completed: isCompleted(spec, state),
      scene_id: state.scene_id,
      task_id: task.id,
      transition_id: null,
    };
  }
  if (!evaluateCondition(spec, state, task.requires)) {
    return reject(state, 'NOT_AVAILABLE', '前置条件尚未满足。', task);
  }

  let extraEffects: readonly Effect[] = [];
  let target: string | undefined;

  if (task.type === 'hotspot') {
    // The action union is restricted: a hotspot action carries no option/order.
    if (input.option_id !== undefined || input.order !== undefined) {
      return reject(state, 'INVALID_ACTION', '热点任务不接受选项或排序输入。', task);
    }
  } else if (task.type === 'choice') {
    if (typeof input.option_id !== 'string') return reject(state, 'INVALID_ACTION', '缺少选项。', task);
    const option = task.options.find((candidate) => candidate.id === input.option_id);
    if (!option) return reject(state, 'INVALID_ACTION', '未知选项。', task);
    if (!option.correct) {
      return {
        result_code: 'WRONG_ANSWER',
        next_state: state,
        feedback: option.feedback,
        completed: false,
        scene_id: state.scene_id,
        task_id: task.id,
        transition_id: null,
      };
    }
    extraEffects = option.on_success;
    target = option.target_scene;
  } else {
    const order = input.order;
    if (!Array.isArray(order) || order.some((value) => typeof value !== 'string')) {
      return reject(state, 'INVALID_ACTION', '排序输入格式错误。', task);
    }
    if (!isCompletePermutation(task.items, order)) {
      return reject(state, 'INVALID_SEQUENCE', '排序必须是完整且不重复的排列。', task);
    }
    if (!satisfiesPrecedence(order, task.precedence)) {
      return {
        result_code: 'WRONG_ANSWER',
        next_state: state,
        feedback: task.feedback.failure,
        completed: false,
        scene_id: state.scene_id,
        task_id: task.id,
        transition_id: null,
      };
    }
  }

  // Completion flag is engine-owned; every effect can only set true.
  let next = withFlags(state, [task.completion_flag]);
  next = applyEffects(next, task.on_success);
  next = applyEffects(next, extraEffects);
  const jumped = tryJump(spec, next, target);
  if (!jumped) return reject(state, 'INCOMPLETE_REQUIREMENTS', '完成条件尚未全部满足。', task);

  return okResult(spec, jumped, task.feedback.success, state.scene_id, task);
}

/** Replay rebuilds the entry state: all flags false, entry scene. */
export function replayState(spec: ExperienceSpecModel): PlayerState {
  return initialState(spec);
}
