/**
 * HTTP client for the 叙境 API.
 *
 * The browser never sees provider credentials or project internals; every call
 * carries the development actor header and errors are normalised to the
 * documented `{error: {code, message}}` envelope so the UI can branch on code
 * rather than on message text.
 */

export interface ApiErrorBody {
  code: string;
  message: string;
  object_id?: string | null;
  retryable?: boolean;
  details?: Record<string, unknown>;
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly retryable: boolean;
  readonly details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = 'ApiError';
    this.code = body.code;
    this.status = status;
    this.retryable = body.retryable ?? false;
    this.details = body.details ?? {};
  }
}

export interface Brief {
  audience: string;
  duration_minutes: number;
  learning_goals: string[];
}

export interface Project {
  id: string;
  name: string;
  brief: Brief;
  brief_revision: number;
  revision_head_id: string | null;
  latest_candidate_version_id: string | null;
  selected_version_id: string | null;
  stable_version_id: string | null;
  active_revision_run_id: string | null;
  created_at: string | null;
}

export interface SourceSummary {
  source_id: string;
  /** The listing endpoint includes the title; the upload response does not. */
  title?: string;
  parse_status: string;
  sha256: string;
  error_code: string | null;
}

export interface Span {
  id: string;
  page: number | null;
  paragraph: number;
  start_cp: number;
  end_cp: number;
  quote: string;
  text_hash: string;
}

export interface Claim {
  id: string;
  revision: number;
  statement: string;
  content_type: 'supported' | 'legend' | 'adaptation' | 'unconfirmed';
  evidence_span_ids: string[];
  qualifier?: string | null;
}

export interface RunSnapshot {
  id: string;
  status: string;
  stage: string;
  attempt: number;
  last_sequence: number;
  budget: { max_calls: number; calls_reserved: number; calls_settled: number; repair_rounds: number };
  error_code: string | null;
}

export interface AgentTaskView {
  task_id: string;
  agent_id: string;
  role: string;
  profile_version: string;
  status: string;
  envelope: { objective: string; allowed_tools: string[]; input_hash: string };
  artifact_refs: string[];
  usage: { model_calls?: number; input_tokens?: number; output_tokens?: number; cost_status?: string };
  result: { status?: string; issues?: unknown[] } | null;
}

export interface VersionSummary {
  id: string;
  parent_id: string | null;
  spec_hash: string;
  semantic_hash: string;
  created_at: string;
}

export interface Citation {
  span_id: string;
  source_id: string;
  label: string;
  quote: string;
  claim_ids: string[];
}

export interface SuggestedAction {
  kind: string;
  label: string;
  scene_id: string | null;
  claim_id: string | null;
  level: number | null;
}

export interface TurnResult {
  turn_id: string;
  status: string;
  final_text: string | null;
  answerability: string | null;
  citations: Citation[];
  suggested_actions: SuggestedAction[];
  cost_status: string;
  events: { sequence: number; type: string; payload: Record<string, unknown> }[];
}

export interface HealthReport {
  status: string;
  environment: string;
  model_provider: string;
  model_configured: boolean;
  simulated: boolean;
  validator_available: boolean;
}

export interface ClientOptions {
  baseUrl?: string;
  actorId?: string;
  fetchImpl?: typeof fetch;
}

export class XujingClient {
  private readonly baseUrl: string;
  private readonly actorId: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options: ClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? '';
    this.actorId = options.actorId ?? '';
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    headers: Record<string, string> = {},
    multipart = false,
  ): Promise<T> {
    const isForm = multipart && body instanceof FormData;
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      method,
      headers: {
        accept: 'application/json',
        // A FormData body must let the browser set the boundary itself.
        ...(body === undefined || isForm ? {} : { 'content-type': 'application/json' }),
        ...(this.actorId ? { 'x-actor-id': this.actorId } : {}),
        ...headers,
      },
      ...(body === undefined ? {} : { body: isForm ? (body as FormData) : JSON.stringify(body) }),
    });
    if (response.status === 204) return undefined as T;
    const text = await response.text();
    let payload: unknown = null;
    try {
      payload = text ? JSON.parse(text) : null;
    } catch {
      throw new ApiError(response.status, {
        code: 'INVALID_RESPONSE',
        message: '服务返回了无法解析的响应。',
      });
    }
    if (!response.ok) {
      const envelope = payload as { error?: ApiErrorBody } | null;
      if (envelope?.error?.code) {
        throw new ApiError(response.status, envelope.error);
      }
      // Not our envelope: name the status so the user sees something actionable
      // instead of an opaque "UNKNOWN".
      throw new ApiError(response.status, {
        code: `HTTP_${response.status}`,
        message:
          response.status === 404
            ? '请求的资源不存在（接口可能未部署）。'
            : response.status === 405
              ? '该接口不接受此请求方法（前端与服务端版本可能不一致）。'
              : `服务返回 ${response.status} ${response.statusText || ''}`.trim(),
        retryable: response.status >= 500,
      });
    }
    return (payload as { data?: T })?.data as T;
  }

  health(): Promise<HealthReport> {
    return this.fetchImpl(`${this.baseUrl}/healthz`).then(async (response) => {
      if (!response.ok) throw new ApiError(response.status, { code: 'HEALTH_FAILED', message: '服务不可用。' });
      return (await response.json()) as HealthReport;
    });
  }

  listProjects(): Promise<Project[]> {
    return this.request<Project[]>('GET', '/api/v1/projects');
  }

  createProject(name: string, brief: Brief): Promise<Project> {
    return this.request<Project>('POST', '/api/v1/projects', { name, brief });
  }

  getProject(id: string): Promise<Project> {
    return this.request<Project>('GET', `/api/v1/projects/${id}`);
  }

  uploadText(
    projectId: string,
    input: { text: string; title: string; license_note: string },
  ): Promise<SourceSummary> {
    return this.request<SourceSummary>('POST', `/api/v1/projects/${projectId}/sources/text`, input);
  }

  uploadFile(projectId: string, file: File, licenseNote: string): Promise<SourceSummary> {
    // multipart: the browser streams the bytes; the server sniffs the real type.
    const body = new FormData();
    body.append('file', file);
    body.append('license_note', licenseNote);
    return this.request<SourceSummary>('POST', `/api/v1/projects/${projectId}/sources`, body, undefined, true);
  }

  extractClaims(
    projectId: string,
    snapshotId: string,
  ): Promise<{ claims: { statement: string; content_type: string }[]; gaps: string[]; cost_status: string }> {
    return this.request('POST', `/api/v1/projects/${projectId}/source-snapshots/${snapshotId}/extract-claims`);
  }

  listSources(projectId: string): Promise<(SourceSummary & { title: string })[]> {
    return this.request('GET', `/api/v1/projects/${projectId}/sources`);
  }

  listSpans(sourceId: string): Promise<Span[]> {
    return this.request<Span[]>('GET', `/api/v1/sources/${sourceId}/spans`);
  }

  listClaims(projectId: string): Promise<Claim[]> {
    return this.request<Claim[]>('GET', `/api/v1/projects/${projectId}/claims`);
  }

  addClaims(
    projectId: string,
    claims: { statement: string; content_type: Claim['content_type']; evidence_span_ids: string[] }[],
  ): Promise<{ id: string; revision: number }[]> {
    return this.request('POST', `/api/v1/projects/${projectId}/claims`, { claims });
  }

  listSnapshots(projectId: string): Promise<{ id: string; sha256: string; created_at: string | null }[]> {
    return this.request('GET', `/api/v1/projects/${projectId}/source-snapshots`);
  }

  createSnapshot(projectId: string, sourceIds: string[]): Promise<{ id: string; sha256: string }> {
    return this.request('POST', `/api/v1/projects/${projectId}/source-snapshots`, { source_ids: sourceIds });
  }

  submitRun(
    projectId: string,
    input: { snapshotId: string; briefRevision: number; instruction: string; autoContinue: boolean },
    idempotencyKey: string,
  ): Promise<{ run_id: string; created: boolean }> {
    return this.request(
      'POST',
      `/api/v1/projects/${projectId}/runs`,
      {
        source_snapshot_id: input.snapshotId,
        brief_revision: input.briefRevision,
        auto_continue: input.autoContinue,
        instruction: input.instruction,
      },
      { 'Idempotency-Key': idempotencyKey },
    );
  }

  getRun(runId: string): Promise<RunSnapshot> {
    return this.request<RunSnapshot>('GET', `/api/v1/runs/${runId}`);
  }

  listAgentTasks(
    runId: string,
  ): Promise<{ plan: { notes: string; tasks: unknown[] } | null; tasks: AgentTaskView[] }> {
    return this.request('GET', `/api/v1/runs/${runId}/agent-tasks`);
  }

  cancelRun(runId: string): Promise<{ id: string; status: string }> {
    return this.request('POST', `/api/v1/runs/${runId}/cancel`);
  }

  listVersions(projectId: string): Promise<VersionSummary[]> {
    return this.request<VersionSummary[]>('GET', `/api/v1/projects/${projectId}/versions`);
  }

  getVersion(versionId: string): Promise<{ id: string; spec: Record<string, unknown>; dialogue_profile: Record<string, unknown> | null; semantic_hash: string; spec_hash: string }> {
    return this.request('GET', `/api/v1/versions/${versionId}`);
  }

  submitReview(
    versionId: string,
    input: { decision: 'approved' | 'needs_changes'; notes: string; coverage_claim_ids: string[]; expected_semantic_hash: string },
  ): Promise<{ id: string; decision: string }> {
    return this.request('POST', `/api/v1/versions/${versionId}/reviews`, input);
  }

  promoteStable(projectId: string, versionId: string): Promise<{ stable_version_id: string }> {
    return this.request('POST', `/api/v1/projects/${projectId}/stable`, { version_id: versionId });
  }

  createShare(versionId: string, licenseAck: boolean, hours = 72): Promise<{ share_id: string; token: string; expires_at: string }> {
    return this.request('POST', `/api/v1/versions/${versionId}/shares`, { version_id: versionId, license_ack: licenseAck, hours });
  }

  revokeShare(shareId: string): Promise<void> {
    return this.request('DELETE', `/api/v1/shares/${shareId}`);
  }

  createCreatorConversation(projectId: string, baseVersionId?: string): Promise<{ conversation_id: string; kind: string }> {
    return this.request('POST', `/api/v1/projects/${projectId}/conversations`, {
      kind: 'creator',
      ...(baseVersionId ? { base_version_id: baseVersionId } : {}),
    });
  }

  submitTurn(conversationId: string, input: { clientTurnId: string; message: string }): Promise<{ turn_id: string; status: string; reused: boolean }> {
    return this.request('POST', `/api/v1/conversations/${conversationId}/turns`, {
      client_turn_id: input.clientTurnId,
      message: input.message,
    });
  }

  runTurn(turnId: string): Promise<TurnResult> {
    return this.request<TurnResult>('POST', `/api/v1/conversation-turns/${turnId}/run`, {});
  }

  cancelTurn(turnId: string): Promise<{ turn_id: string; status: string }> {
    return this.request('POST', `/api/v1/conversation-turns/${turnId}/cancel`);
  }
}

/**
 * A turn's event log is authoritative: partial deltas must never be shown as a
 * finished answer, so the UI derives its message from the terminal event only.
 */
export function finalMessageFromTurn(result: TurnResult): { text: string; citations: Citation[]; answerability: string } | null {
  const completed = result.events.find((event) => event.type === 'completed');
  if (!completed || result.status !== 'succeeded' || !result.final_text) return null;
  return {
    text: result.final_text,
    citations: result.citations,
    answerability: result.answerability ?? 'unknown',
  };
}
