/**
 * Player-side client for a shared, frozen experience version.
 *
 * A participant can only read the manifest of the shared version and talk to
 * its Guide. There is no project access here, and every participant-visible
 * answer carries server-mapped citations.
 */
import type { ExperienceSpec } from '../../../../packages/contracts/index.ts';
import type { DialogueProfile } from '../../../../packages/contracts/index.ts';

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

export interface GuideTurnResult {
  turn_id: string;
  status: string;
  final_text: string | null;
  answerability: string | null;
  citations: Citation[];
  suggested_actions: SuggestedAction[];
  cost_status: string;
  events: { sequence: number; type: string; payload: Record<string, unknown> }[];
}

export interface ShareManifest {
  version_id: string;
  spec: ExperienceSpec;
  dialogue_profile: DialogueProfile | null;
  spec_hash: string;
}

export class PlayerError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'PlayerError';
    this.status = status;
    this.code = code;
  }
}

export interface PlayerClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}

export class PlayerClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options: PlayerClientOptions = {}) {
    this.baseUrl = options.baseUrl ?? '';
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
  }

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      method,
      headers: {
        accept: 'application/json',
        ...(body === undefined ? {} : { 'content-type': 'application/json' }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const text = await response.text();
    let payload: unknown = null;
    try {
      payload = text ? JSON.parse(text) : null;
    } catch {
      throw new PlayerError(response.status, 'INVALID_RESPONSE', '服务返回了无法解析的响应。');
    }
    if (!response.ok) {
      const error = (payload as { error?: { code: string; message: string } } | null)?.error;
      throw new PlayerError(response.status, error?.code ?? 'UNKNOWN', error?.message ?? '请求失败。');
    }
    return (payload as { data?: T })?.data as T;
  }

  manifest(token: string): Promise<ShareManifest> {
    return this.request<ShareManifest>('GET', `/api/v1/share/${encodeURIComponent(token)}/manifest`);
  }

  openSession(token: string): Promise<{ session_id: string; version_id: string; expires_at: string | null }> {
    return this.request('POST', `/api/v1/share/${encodeURIComponent(token)}/sessions`);
  }

  openGuideConversation(experienceSessionId: string): Promise<{ conversation_id: string; kind: string; version_id: string }> {
    return this.request('POST', `/api/v1/experience-sessions/${encodeURIComponent(experienceSessionId)}/conversations`, {
      kind: 'guide',
    });
  }

  submitTurn(conversationId: string, clientTurnId: string, message: string): Promise<{ turn_id: string; status: string }> {
    return this.request('POST', `/api/v1/conversations/${encodeURIComponent(conversationId)}/turns`, {
      client_turn_id: clientTurnId,
      message,
    });
  }

  runTurn(turnId: string): Promise<GuideTurnResult> {
    return this.request('POST', `/api/v1/conversation-turns/${encodeURIComponent(turnId)}/run`, {});
  }

  cancelTurn(turnId: string): Promise<{ turn_id: string; status: string }> {
    return this.request('POST', `/api/v1/conversation-turns/${encodeURIComponent(turnId)}/cancel`);
  }
}

/**
 * Guide answers are only shown when the turn reached a completed event.
 * A partial stream is never presented as an answer.
 */
export function guideAnswer(result: GuideTurnResult): { text: string; citations: Citation[]; answerability: string } | null {
  const completed = result.events.find((event) => event.type === 'completed');
  if (!completed || result.status !== 'succeeded' || !result.final_text) return null;
  return { text: result.final_text, citations: result.citations, answerability: result.answerability ?? 'unknown' };
}
