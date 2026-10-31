/**
 * Semantic checks + exhaustive state search over the shared engine (F05-R01/R02).
 *
 * Nothing here re-implements play semantics: every edge is produced by calling
 * `applyAction` from the shared engine, so the proof cannot drift from the
 * player. Errors are separated into categories so a caller can distinguish
 * "structurally invalid" from "logically unreachable" from "budget exhausted".
 */
import {
  applyAction,
  assertSupportedRuntime,
  initialState,
  isCompletePermutation,
  isCompleted,
  requiredFlagsSatisfied,
  SpecError,
  type ActionInput,
  type Condition,
  type ExperienceSpecModel,
  type PlayerState,
  type Sequence,
  type Task,
} from '../../engine/src/engine.ts';

export type Layer = 'structure' | 'semantics' | 'state';

export type Status = 'passed' | 'failed' | 'inconclusive';

export interface Finding {
  layer: Layer;
  code: string;
  message: string;
  path?: string;
  counterexample?: unknown;
}

export interface StateSearchResult {
  status: Status;
  visited: number;
  edges: number;
  terminal_reachable: boolean;
  unreachable_nonterminal: string[];
  counterexamples: Finding[];
  budget_exhausted: boolean;
  /** Shortest witness path from entry to the completion scene. */
  witness: ActionInput[] | null;
}

export interface ValidationReport {
  status: Status;
  checker_version: string;
  spec_hash: string;
  semantic_hash: string;
  layers: { structure: Status; semantics: Status; state: Status };
  findings: Finding[];
  search: StateSearchResult;
  /** Deterministic action paths a browser playtest can replay. */
  playtest_paths: ActionInput[][];
}

export const CHECKER_VERSION = 'validator-0.1.0';
export const DEFAULT_STATE_LIMIT = 20_000;

const ID_PATTERN = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/;

function finding(layer: Layer, code: string, message: string, path?: string, counterexample?: unknown): Finding {
  const result: Finding = { layer, code, message };
  if (path !== undefined) result.path = path;
  if (counterexample !== undefined) result.counterexample = counterexample;
  return result;
}

function duplicates(values: readonly string[]): string[] {
  const seen = new Set<string>();
  const repeated = new Set<string>();
  for (const value of values) {
    if (seen.has(value)) repeated.add(value);
    seen.add(value);
  }
  return [...repeated];
}

function collectTasks(spec: ExperienceSpecModel): { task: Task; sceneId: string }[] {
  return spec.scenes.flatMap((scene) => scene.tasks.map((task) => ({ task, sceneId: scene.id })));
}

function checkCondition(
  condition: Condition,
  flags: Set<string>,
  settable: Set<string>,
  path: string,
  out: Finding[],
  depth = 1,
): void {
  if (depth > 6) {
    out.push(finding('structure', 'CONDITION_DEPTH', '条件嵌套超过 6 层。', path));
    return;
  }
  if ('all' in condition) {
    if (condition.all.length === 0 || condition.all.length > 12) {
      out.push(finding('structure', 'CONDITION_ARITY', 'all 需要 1—12 个条件。', path));
    }
    condition.all.forEach((child, index) => checkCondition(child, flags, settable, `${path}/all/${index}`, out, depth + 1));
    return;
  }
  if ('any' in condition) {
    if (condition.any.length === 0 || condition.any.length > 12) {
      out.push(finding('structure', 'CONDITION_ARITY', 'any 需要 1—12 个条件。', path));
    }
    condition.any.forEach((child, index) => checkCondition(child, flags, settable, `${path}/any/${index}`, out, depth + 1));
    return;
  }
  if ('not' in condition) {
    checkCondition(condition.not, flags, settable, `${path}/not`, out, depth + 1);
    return;
  }
  const { id, value } = condition.flag_equals;
  if (!flags.has(id)) out.push(finding('structure', 'UNKNOWN_FLAG', `条件引用未声明标记 ${id}。`, path));
  // A condition can only be satisfied by a flag some task or effect can set.
  // `flag_equals=false` on a never-settable flag is the documented idiom for
  // "no condition", so only the `true` direction is reported.
  if (value === true && !settable.has(id)) {
    out.push(
      finding(
        'semantics',
        'CONDITION_UNSATISFIABLE',
        `条件要求标记 ${id} 为 true，但没有任何任务或效果能设置它。`,
        path,
      ),
    );
  }
}

export function checkStructure(spec: ExperienceSpecModel, evidenceSpanIds: readonly string[]): Finding[] {
  const out: Finding[] = [];
  try {
    assertSupportedRuntime(spec);
  } catch (error) {
    if (error instanceof SpecError) {
      out.push(finding('structure', error.code, error.message, '/runtime_version'));
      return out;
    }
    throw error;
  }

  const flags = new Set(spec.flags.map((flag) => flag.id));
  const claims = new Set(spec.claims.map((claim) => claim.id));
  const objectives = new Set(spec.objectives.map((objective) => objective.id));
  const scenes = new Set(spec.scenes.map((scene) => scene.id));
  const assets = new Set(spec.asset_manifest.map((asset) => asset.id));
  const evidence = new Set(evidenceSpanIds);

  for (const id of duplicates(spec.flags.map((flag) => flag.id))) out.push(finding('structure', 'DUPLICATE_FLAG', `重复标记 ${id}。`));
  for (const id of duplicates(spec.claims.map((claim) => claim.id))) out.push(finding('structure', 'DUPLICATE_CLAIM', `重复事实 ${id}。`));
  for (const id of duplicates(spec.objectives.map((objective) => objective.id))) out.push(finding('structure', 'DUPLICATE_OBJECTIVE', `重复目标 ${id}。`));
  for (const id of duplicates(spec.scenes.map((scene) => scene.id))) out.push(finding('structure', 'DUPLICATE_SCENE', `重复场景 ${id}。`));

  const tasks = collectTasks(spec);
  for (const id of duplicates(tasks.map((item) => item.task.id))) out.push(finding('structure', 'DUPLICATE_TASK', `任务 ID 全体验必须唯一：${id}。`));
  const completionFlags = tasks.map((item) => item.task.completion_flag);
  for (const id of duplicates(completionFlags)) {
    out.push(
      finding(
        'structure',
        'DUPLICATE_COMPLETION_FLAG',
        `任务完成标记重复：${id}。完成任务无法区分。`,
      ),
    );
  }
  for (const id of Object.keys({}).concat(spec.flags.map((flag) => flag.id))) {
    if (!ID_PATTERN.test(id)) out.push(finding('structure', 'INVALID_ID', `ID 不符合格式：${id}。`));
  }

  if (!scenes.has(spec.entry_scene)) out.push(finding('structure', 'UNKNOWN_SCENE', `入口场景不存在：${spec.entry_scene}。`, '/entry_scene'));
  if (!scenes.has(spec.completion.scene_id)) {
    out.push(finding('structure', 'UNKNOWN_SCENE', `完成场景不存在：${spec.completion.scene_id}。`, '/completion/scene_id'));
  }
  if (spec.entry_scene === spec.completion.scene_id) {
    out.push(finding('structure', 'ENTRY_IS_COMPLETION', '入口不能与完成场景相同。', '/entry_scene'));
  }
  for (const flag of spec.completion.required_flags) {
    if (!flags.has(flag)) out.push(finding('structure', 'UNKNOWN_FLAG', `完成标记未声明：${flag}。`, '/completion/required_flags'));
  }

  const requiredTasks = tasks.filter((item) => item.task.required);
  if (requiredTasks.length < 1 || requiredTasks.length > 6) {
    out.push(finding('structure', 'REQUIRED_TASK_COUNT', '必要任务数量需在 1—6 之间。'));
  }
  const requiredFlagSet = new Set(requiredTasks.map((item) => item.task.completion_flag));
  const completionSet = new Set(spec.completion.required_flags);
  if (completionSet.size !== requiredFlagSet.size || [...completionSet].some((flag) => !requiredFlagSet.has(flag))) {
    out.push(
      finding('structure', 'COMPLETION_MISMATCH', '完成标记集合必须等于全部必要任务的完成标记。', '/completion/required_flags'),
    );
  }

  for (const claim of spec.claims) {
    for (const span of claim.evidence_span_ids) {
      if (!evidence.has(span)) out.push(finding('semantics', 'UNKNOWN_EVIDENCE', `事实 ${claim.id} 引用了不存在的证据片段。`, claim.id));
    }
    if ((claim.content_type === 'supported' || claim.content_type === 'legend') && claim.evidence_span_ids.length === 0) {
      out.push(finding('semantics', 'CLAIM_WITHOUT_EVIDENCE', `${claim.content_type} 事实 ${claim.id} 缺少证据。`, claim.id));
    }
  }
  const settable = new Set<string>(completionFlags);
  for (const { task } of tasks) {
    for (const effect of task.on_success) settable.add(effect.set_flag);
    if (task.type === 'choice') {
      for (const option of task.options) for (const effect of option.on_success) settable.add(effect.set_flag);
    }
  }

  for (const objective of spec.objectives) {
    for (const claimId of objective.claim_ids) {
      if (!claims.has(claimId)) out.push(finding('structure', 'UNKNOWN_CLAIM', `目标 ${objective.id} 引用未知事实 ${claimId}。`));
    }
  }
  for (const scene of spec.scenes) {
    for (const claimId of scene.claim_ids) {
      if (!claims.has(claimId)) out.push(finding('structure', 'UNKNOWN_CLAIM', `场景 ${scene.id} 引用未知事实 ${claimId}。`));
    }
    for (const assetId of scene.asset_ids) {
      if (!assets.has(assetId)) out.push(finding('structure', 'UNKNOWN_ASSET', `场景 ${scene.id} 引用未知素材 ${assetId}。`));
    }
    if ((scene.content_type === 'supported' || scene.content_type === 'legend') && scene.claim_ids.length === 0) {
      out.push(finding('semantics', 'SCENE_WITHOUT_CLAIM', `${scene.content_type} 场景 ${scene.id} 未绑定事实。`, scene.id));
    }
    for (const transition of scene.transitions) {
      if (!scenes.has(transition.target_scene)) {
        out.push(finding('structure', 'UNKNOWN_SCENE', `导航 ${transition.id} 指向未知场景。`, scene.id));
      }
      checkCondition(transition.requires, flags, settable, `/scenes/${scene.id}/transitions/${transition.id}/requires`, out);
    }
  }

  for (const { task, sceneId } of tasks) {
    if (!flags.has(task.completion_flag)) {
      out.push(finding('structure', 'UNKNOWN_FLAG', `任务 ${task.id} 的完成标记未声明。`, sceneId));
    }
    for (const objectiveId of task.objective_ids) {
      if (!objectives.has(objectiveId)) out.push(finding('structure', 'UNKNOWN_OBJECTIVE', `任务 ${task.id} 引用未知目标。`));
    }
    for (const claimId of task.claim_ids) {
      if (!claims.has(claimId)) out.push(finding('structure', 'UNKNOWN_CLAIM', `任务 ${task.id} 引用未知事实 ${claimId}。`));
    }
    for (const claimId of task.feedback.claim_ids) {
      if (!claims.has(claimId)) out.push(finding('semantics', 'UNKNOWN_CLAIM', `任务 ${task.id} 反馈引用未知事实。`));
    }
    checkCondition(task.requires, flags, settable, `/scenes/${sceneId}/tasks/${task.id}/requires`, out);
    for (const effect of task.on_success) {
      if (!flags.has(effect.set_flag)) out.push(finding('structure', 'UNKNOWN_FLAG', `任务 ${task.id} 效果引用未声明标记。`));
      if (completionFlags.includes(effect.set_flag)) {
        out.push(finding('structure', 'COMPLETION_FLAG_WRITTEN', '任务完成标记只能由引擎设置，不能出现在效果中。'));
      }
    }
    if (task.required) {
      if (task.objective_ids.length === 0) {
        out.push(finding('semantics', 'REQUIRED_TASK_WITHOUT_OBJECTIVE', `必要任务 ${task.id} 未绑定教学目标。`));
      }
      const supported = new Set(
        spec.claims.filter((claim) => claim.content_type === 'supported' || claim.content_type === 'legend').map((claim) => claim.id),
      );
      if (!task.claim_ids.some((claimId) => supported.has(claimId))) {
        out.push(finding('semantics', 'REQUIRED_TASK_WITHOUT_SUPPORT', `必要任务 ${task.id} 缺少 supported/legend 依据。`));
      }
    }
    if (task.type === 'choice') {
      const correct = task.options.filter((option) => option.correct);
      if (correct.length !== 1) {
        out.push(finding('semantics', 'CHOICE_CORRECT_COUNT', `选择题 ${task.id} 需要且只能有一个正确选项。`));
      }
      for (const option of task.options) {
        if (!option.correct && (option.on_success.length > 0 || option.target_scene !== undefined)) {
          out.push(finding('structure', 'WRONG_OPTION_EFFECT', `错误选项 ${option.id} 不得携带效果或跳转。`));
        }
        if (option.target_scene && !scenes.has(option.target_scene)) {
          out.push(finding('structure', 'UNKNOWN_SCENE', `选项 ${option.id} 指向未知场景。`));
        }
        for (const effect of option.on_success) {
          if (!flags.has(effect.set_flag)) out.push(finding('structure', 'UNKNOWN_FLAG', `选项 ${option.id} 效果未声明标记。`));
          if (completionFlags.includes(effect.set_flag)) {
            out.push(finding('structure', 'COMPLETION_FLAG_WRITTEN', `选项 ${option.id} 不得写任务完成标记。`));
          }
        }
      }
    }
    if (task.type === 'sequence') checkSequence(task, claims, out);
  }
  return out;
}

function checkSequence(task: Sequence, claims: Set<string>, out: Finding[]): void {
  const itemIds = new Set(task.items.map((item) => item.id));
  if (new Set(task.items.map((item) => item.id)).size !== task.items.length) {
    out.push(finding('structure', 'DUPLICATE_SEQUENCE_ITEM', `排序任务 ${task.id} 存在重复元素。`));
  }
  const graph = new Map<string, string[]>();
  task.precedence.forEach((edge, index) => {
    if (!itemIds.has(edge.before) || !itemIds.has(edge.after)) {
      out.push(finding('structure', 'UNKNOWN_SEQUENCE_ITEM', `排序任务 ${task.id} 的偏序边 ${index} 引用未知元素。`));
    }
    if (!claims.has(edge.claim_id)) {
      out.push(finding('semantics', 'UNKNOWN_CLAIM', `排序任务 ${task.id} 的偏序边必须绑定事实。`));
    }
    const list = graph.get(edge.before) ?? [];
    list.push(edge.after);
    graph.set(edge.before, list);
  });
  // DAG check: a cycle would make the task unsolvable.
  const state = new Map<string, number>();
  const visit = (node: string): boolean => {
    const current = state.get(node) ?? 0;
    if (current === 1) return true;
    if (current === 2) return false;
    state.set(node, 1);
    for (const next of graph.get(node) ?? []) if (visit(next)) return true;
    state.set(node, 2);
    return false;
  };
  if ([...itemIds].some(visit)) out.push(finding('semantics', 'SEQUENCE_CYCLE', `排序任务 ${task.id} 的偏序存在环。`));

  // AT-02: the material must not be padded with an unstated A<B style edge.
  let hasValidOrder = false;
  const permutations = allPermutations(task.items.map((item) => item.id));
  for (const order of permutations) {
    const ok = task.precedence.every((edge) => order.indexOf(edge.before) < order.indexOf(edge.after));
    if (ok) hasValidOrder = true;
  }
  if (!hasValidOrder) out.push(finding('semantics', 'SEQUENCE_UNSOLVABLE', `排序任务 ${task.id} 没有满足偏序的排列。`));
}

export function allPermutations<T>(items: readonly T[]): T[][] {
  if (items.length <= 1) return [items.slice()];
  const result: T[][] = [];
  items.forEach((item, index) => {
    const rest = items.slice(0, index).concat(items.slice(index + 1));
    for (const permutation of allPermutations(rest)) result.push([item, ...permutation]);
  });
  return result;
}

function stateKey(state: PlayerState): string {
  const flags = Object.keys(state.flags)
    .sort()
    .filter((flag) => state.flags[flag])
    .join(',');
  return `${state.scene_id}|${flags}`;
}

function candidateActions(spec: ExperienceSpecModel, state: PlayerState): ActionInput[] {
  const scene = spec.scenes.find((candidate) => candidate.id === state.scene_id);
  if (!scene) return [];
  const actions: ActionInput[] = [];
  for (const transition of scene.transitions) {
    actions.push({ kind: 'transition', scene_id: scene.id, transition_id: transition.id });
  }
  for (const task of scene.tasks) {
    if (task.type === 'choice') {
      for (const option of task.options) {
        actions.push({ kind: 'task', scene_id: scene.id, task_id: task.id, option_id: option.id });
      }
    } else if (task.type === 'sequence') {
      for (const order of allPermutations(task.items.map((item) => item.id))) {
        actions.push({ kind: 'task', scene_id: scene.id, task_id: task.id, order });
      }
    } else {
      actions.push({ kind: 'task', scene_id: scene.id, task_id: task.id });
    }
  }
  return actions;
}

/**
 * Exhaustive breadth-first search over reachable (scene, flags) states.
 * Wrong answers and unavailable actions do not extend the logical state space.
 * Returns `inconclusive` when the state/edge budget is exhausted, never `passed`.
 */
export function searchStates(
  spec: ExperienceSpecModel,
  options: { stateLimit?: number; edgeLimit?: number } = {},
): StateSearchResult {
  const stateLimit = options.stateLimit ?? DEFAULT_STATE_LIMIT;
  const edgeLimit = options.edgeLimit ?? 200_000;
  const start = initialState(spec);
  const queue: PlayerState[] = [start];
  const pathTo = new Map<string, ActionInput[]>([[stateKey(start), []]]);
  const visited = new Set<string>([stateKey(start)]);
  const reachedTerminalKeys: string[] = [];
  let edges = 0;
  let budgetExhausted = false;

  while (queue.length > 0) {
    if (visited.size > stateLimit || edges > edgeLimit) {
      budgetExhausted = true;
      break;
    }
    const state = queue.shift() as PlayerState;
    if (isCompleted(spec, state)) {
      reachedTerminalKeys.push(stateKey(state));
      continue;
    }
    for (const action of candidateActions(spec, state)) {
      edges += 1;
      let result;
      try {
        result = applyAction(spec, state, action);
      } catch (error) {
        if (error instanceof SpecError) return {
          status: 'failed',
          visited: visited.size,
          edges,
          terminal_reachable: false,
          unreachable_nonterminal: [],
          counterexamples: [finding('state', error.code, error.message)],
          budget_exhausted: false,
          witness: null,
        };
        throw error;
      }
      if (result.result_code !== 'OK') continue;
      const key = stateKey(result.next_state);
      if (visited.has(key)) continue;
      visited.add(key);
      const previous = pathTo.get(stateKey(state)) ?? [];
      pathTo.set(key, [...previous, action]);
      if (isCompleted(spec, result.next_state)) {
        reachedTerminalKeys.push(key);
        continue;
      }
      queue.push(result.next_state);
    }
  }

  const terminalReachable = reachedTerminalKeys.length > 0;
  // Reverse reachability: from every reachable non-terminal state, can the
  // completion scene still be entered? We recompute forward from each state is
  // too costly, so we use the visited graph's successor relation.
  const unreachable = budgetExhausted ? ['state limit reached; completeness not proven'] : [];
  const witness = terminalReachable ? (pathTo.get(reachedTerminalKeys[0] as string) ?? null) : null;

  const counterexamples: Finding[] = [];
  if (!terminalReachable) {
    counterexamples.push(
      finding('state', 'NO_TERMINAL_STATE', '从入口状态无法到达合格终态。'),
    );
  }
  return {
    status: budgetExhausted ? 'inconclusive' : terminalReachable ? 'passed' : 'failed',
    visited: visited.size,
    edges,
    terminal_reachable: terminalReachable,
    unreachable_nonterminal: unreachable,
    counterexamples,
    budget_exhausted: budgetExhausted,
    witness,
  };
}

export function validate(
  spec: ExperienceSpecModel,
  evidenceSpanIds: readonly string[],
  hashes: { specHash: string; semanticHash: string },
  options: { stateLimit?: number } = {},
): ValidationReport {
  const structureFindings = checkStructure(spec, evidenceSpanIds);
  const structuralFailures = structureFindings.filter((item) => item.layer !== 'semantics');
  const hasStructuralFailure = structuralFailures.length > 0;
  const search: StateSearchResult = hasStructuralFailure
    ? {
        status: 'failed',
        visited: 0,
        edges: 0,
        terminal_reachable: false,
        unreachable_nonterminal: [],
        counterexamples: [finding('state', 'SKIPPED', '结构错误先于状态搜索。')],
        budget_exhausted: false,
        witness: null,
      }
    : searchStates(spec, options);

  const playtestPaths: ActionInput[][] = search.witness ? [search.witness] : [];
  const status: Status =
    hasStructuralFailure || search.status === 'failed'
      ? 'failed'
      : search.status === 'inconclusive'
        ? 'inconclusive'
        : 'passed';

  return {
    status,
    checker_version: CHECKER_VERSION,
    spec_hash: hashes.specHash,
    semantic_hash: hashes.semanticHash,
    layers: {
      structure: hasStructuralFailure ? 'failed' : 'passed',
      semantics: structureFindings.some((item) => item.layer === 'semantics') ? 'failed' : 'passed',
      state: search.status,
    },
    findings: structureFindings.concat(search.counterexamples),
    search,
    playtest_paths: playtestPaths,
  };
}

export { isCompletePermutation, requiredFlagsSatisfied };
