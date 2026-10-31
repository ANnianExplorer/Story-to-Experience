/**
 * Canonical JSON (RFC 8785 subset) shared with the Python backend.
 *
 * Hashes must be identical across languages, so this module mirrors
 * `server/domain/canonical_json.py`: UTF-16 key ordering, no insignificant
 * whitespace, shortest escapes, integers only. A cross-language golden fixture
 * test locks the two implementations together (G03).
 */
export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export class CanonicalJsonError extends Error {
  readonly code = 'NON_CANONICAL_JSON';

  constructor(message: string) {
    super(message);
    this.name = 'CanonicalJsonError';
  }
}

function escapeString(value: string): string {
  return JSON.stringify(value);
}

function serialize(value: unknown): string {
  if (value === null) return 'null';
  if (value === true) return 'true';
  if (value === false) return 'false';
  if (typeof value === 'number') {
    if (!Number.isInteger(value)) {
      throw new CanonicalJsonError('规范 JSON 不接受浮点数，请使用整数或定点字符串。');
    }
    return String(value);
  }
  if (typeof value === 'string') return escapeString(value);
  if (Array.isArray(value)) return '[' + value.map(serialize).join(',') + ']';
  if (typeof value === 'object') {
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) {
      // Dates, Maps, class instances etc. would silently serialise as "{}" and
      // make two different values hash the same.
      throw new CanonicalJsonError('规范 JSON 只接受纯对象、数组、字符串、整数与布尔值。');
    }
    const record = value as Record<string, unknown>;
    const keys = Object.keys(record).sort(compareUtf16);
    return '{' + keys.map((key) => `${escapeString(key)}:${serialize(record[key])}`).join(',') + '}';
  }
  throw new CanonicalJsonError(`规范 JSON 不支持的类型：${typeof value}`);
}

/** Compare by UTF-16 code units — RFC 8785's ordering, which differs from code points. */
function compareUtf16(left: string, right: string): number {
  if (left === right) return 0;
  const length = Math.min(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    const a = left.charCodeAt(index);
    const b = right.charCodeAt(index);
    if (a !== b) return a - b;
  }
  return left.length - right.length;
}

export function canonicalJson(value: unknown): string {
  return serialize(value);
}

/** SHA-256 of the canonical UTF-8 bytes, hex encoded. Uses WebCrypto (async). */
export async function canonicalSha256(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(canonicalJson(value));
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}
