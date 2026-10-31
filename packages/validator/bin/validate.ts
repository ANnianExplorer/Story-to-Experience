/**
 * Restricted JSON bridge used by the Python backend (ADR-0004):
 * stdin → ``{spec, evidence_span_ids, spec_hash, semantic_hash, state_limit}``
 * stdout → one JSON object (the validation report) or ``{error: {...}}``.
 * No code, paths or commands are accepted from the caller.
 */
import { readFileSync } from 'node:fs';

import { SpecError, type ExperienceSpecModel } from '../../engine/src/engine.ts';
import { validate } from '../src/validator.ts';

interface Request {
  protocol_version?: string;
  spec?: ExperienceSpecModel;
  evidence_span_ids?: string[];
  spec_hash?: string;
  semantic_hash?: string;
  state_limit?: number;
}

function emit(payload: unknown, status: number): void {
  process.stdout.write(JSON.stringify(payload));
  process.exitCode = status;
}

let request: Request;
try {
  request = JSON.parse(readFileSync(0, 'utf8')) as Request;
} catch {
  emit({ error: { code: 'INVALID_JSON', message: '请求不是合法 JSON。' } }, 2);
  request = {};
}

if (request.protocol_version !== '1.0.0') {
  emit({ error: { code: 'PROTOCOL_VERSION_UNSUPPORTED', message: '仅支持 1.0.0。' } }, 2);
} else if (!request.spec || !Array.isArray(request.evidence_span_ids) || !request.spec_hash || !request.semantic_hash) {
  emit({ error: { code: 'INVALID_REQUEST', message: '缺少 spec/证据/哈希。' } }, 2);
} else {
  try {
    const report = validate(
      request.spec,
      request.evidence_span_ids,
      { specHash: request.spec_hash, semanticHash: request.semantic_hash },
      request.state_limit === undefined ? {} : { stateLimit: request.state_limit },
    );
    emit({ protocol_version: '1.0.0', report }, 0);
  } catch (error) {
    if (error instanceof SpecError) {
      emit({ error: { code: error.code, message: error.message } }, 1);
    } else {
      emit({ error: { code: 'INTERNAL', message: error instanceof Error ? error.message : '未知错误' } }, 1);
    }
  }
}
