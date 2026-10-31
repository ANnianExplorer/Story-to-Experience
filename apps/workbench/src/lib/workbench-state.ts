/**
 * Workbench state machine: creator flow from material to a reviewed candidate.
 *
 * Kept framework-free so the behaviour is testable without a browser. Every
 * transition is derived from server responses; the UI only renders it.
 */
import type { AgentTaskView, Claim, Project, RunSnapshot, Span, VersionSummary } from './api.ts';

export type WorkbenchStage =
  | 'idle'
  | 'project_ready'
  | 'material_ready'
  | 'snapshot_ready'
  | 'generating'
  | 'candidate_ready'
  | 'reviewing'
  | 'stable'
  | 'error';

export interface WorkbenchState {
  stage: WorkbenchStage;
  project: Project | null;
  sourceId: string | null;
  spans: Span[];
  claims: Claim[];
  snapshotId: string | null;
  run: RunSnapshot | null;
  agentTasks: AgentTaskView[];
  planNotes: string | null;
  versions: VersionSummary[];
  selectedVersionId: string | null;
  error: { code: string; message: string } | null;
  /** Set when the run ended in a non-success terminal state. */
  runOutcome: 'pending' | 'succeeded' | 'failed' | 'cancelled';
}

export const initialState: WorkbenchState = {
  stage: 'idle',
  project: null,
  sourceId: null,
  spans: [],
  claims: [],
  snapshotId: null,
  run: null,
  agentTasks: [],
  planNotes: null,
  versions: [],
  selectedVersionId: null,
  error: null,
  runOutcome: 'pending',
};

export type WorkbenchAction =
  | { type: 'project_created'; project: Project }
  | { type: 'material_parsed'; sourceId: string; spans: Span[] }
  | { type: 'material_failed'; code: string; message: string }
  | { type: 'claims_updated'; claims: Claim[] }
  | { type: 'snapshot_created'; snapshotId: string }
  | { type: 'state_restored'; snapshotId: string | null }
  | { type: 'snapshot_restored'; snapshotId: string }
  | { type: 'run_queued'; run: RunSnapshot }
  | { type: 'run_updated'; run: RunSnapshot }
  | { type: 'agent_tasks'; tasks: AgentTaskView[]; planNotes?: string | null }
  | { type: 'candidate_ready'; versions: VersionSummary[]; selectedVersionId: string }
  | { type: 'review_submitted' }
  | { type: 'stable'; project: Project }
  | { type: 'error'; code: string; message: string }
  | { type: 'reset' };

export function reduce(state: WorkbenchState, action: WorkbenchAction): WorkbenchState {
  switch (action.type) {
    case 'project_created':
      return { ...initialState, stage: 'project_ready', project: action.project };
    case 'material_parsed':
      return {
        ...state,
        stage: 'material_ready',
        sourceId: action.sourceId,
        spans: action.spans,
        error: null,
      };
    case 'material_failed':
      return { ...state, stage: 'error', error: { code: action.code, message: action.message } };
    case 'claims_updated':
      return { ...state, claims: action.claims, error: null };
    case 'snapshot_created':
      return { ...state, stage: 'snapshot_ready', snapshotId: action.snapshotId, error: null };
    case 'state_restored':
    case 'snapshot_restored':
      // A reloaded page has no in-memory snapshot id; without this the generate
      // button stayed disabled even though the server already had a snapshot.
      return action.snapshotId
        ? {
            ...state,
            stage: state.stage === 'idle' || state.stage === 'error' ? 'snapshot_ready' : state.stage,
            snapshotId: action.snapshotId,
            error: null,
          }
        : state;
    case 'run_queued':
      return { ...state, stage: 'generating', run: action.run, runOutcome: 'pending', error: null };
    case 'run_updated': {
      const status = action.run.status;
      const terminal = status === 'succeeded' || status === 'failed' || status === 'cancelled';
      return {
        ...state,
        run: action.run,
        runOutcome: terminal ? (status as WorkbenchState['runOutcome']) : 'pending',
      };
    }
    case 'agent_tasks':
      return { ...state, agentTasks: action.tasks, planNotes: action.planNotes ?? state.planNotes };
    case 'candidate_ready':
      return {
        ...state,
        stage: 'candidate_ready',
        versions: action.versions,
        selectedVersionId: action.selectedVersionId,
        runOutcome: 'succeeded',
      };
    case 'review_submitted':
      return { ...state, stage: 'reviewing' };
    case 'stable':
      return { ...state, stage: 'stable', project: action.project };
    case 'error':
      return { ...state, stage: 'error', error: { code: action.code, message: action.message } };
    case 'reset':
      return initialState;
    default:
      return state;
  }
}

/** Human-readable stage labels; the UI must never invent a "done" state. */
export const STAGE_LABEL: Record<WorkbenchStage, string> = {
  idle: '未开始',
  project_ready: '项目已创建',
  material_ready: '资料已解析',
  snapshot_ready: '证据已冻结',
  generating: '生成中',
  candidate_ready: '候选待审',
  reviewing: '审核记录已提交',
  stable: '稳定版',
  error: '出错了',
};

/**
 * Canonical gate copy. Tests and UI both read these, so a wording change
 * cannot silently leave two different sentences in the product.
 */
export const GATE_COPY = {
  noMaterial: '尚未上传资料',
  noClaims: '还没有标为事实的证据片段',
  noSnapshot: '还需要冻结证据快照才能开始生成',
  busy: '生成进行中，完成后才能再次提交',
} as const;

export interface ProjectGate {
  canFreeze: boolean;
  canGenerate: boolean;
  reasons: string[];
}

/** F03-R04 / F07-R04: explicit gates instead of optimistic buttons. */
/**
 * Decide what the creator may do next, and say *which* step is missing.
 *
 * The reasons list is what the user actually reads, so it must name the next
 * blocking step rather than the earliest historical one. A reloaded project
 * holds claims (and often versions) with no in-memory upload record; telling
 * that user "尚未上传资料" was wrong and hid the real blocker.
 */
export function gates(state: WorkbenchState): ProjectGate {
  const readyClaims = state.claims.filter((claim) => claim.evidence_span_ids.length > 0);
  const hasMaterial = Boolean(state.sourceId) || readyClaims.length > 0 || state.spans.length > 0;
  const inFlight = state.stage === 'generating' && state.runOutcome === 'pending';
  const reasons: string[] = [];

  if (!hasMaterial) {
    reasons.push(GATE_COPY.noMaterial);
  } else if (readyClaims.length === 0) {
    // Claims gate the freeze step, so this is the earliest actionable blocker.
    reasons.push(GATE_COPY.noClaims);
  } else if (!state.snapshotId) {
    reasons.push(GATE_COPY.noSnapshot);
  } else if (inFlight) {
    reasons.push(GATE_COPY.busy);
  }

  const canFreeze = hasMaterial && readyClaims.length > 0 && !state.snapshotId;
  // Generating requires a frozen snapshot and no *in-flight* run. A failed or
  // cancelled attempt leaves `runOutcome` terminal, so it may be retried.
  const canGenerate = Boolean(state.snapshotId) && readyClaims.length > 0 && !inFlight;
  return { canFreeze, canGenerate, reasons };
}

export function formatCost(budget: RunSnapshot['budget'] | undefined): string {
  if (!budget) return '—';
  return `${budget.calls_settled}/${budget.max_calls} 次调用 · 修复 ${budget.repair_rounds}/2 轮`;
}
