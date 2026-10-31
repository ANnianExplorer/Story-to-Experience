import assert from 'node:assert/strict';
import test from 'node:test';

import { canonicalJson, canonicalSha256, CanonicalJsonError } from '../src/canonical.ts';

test('matches the Python backend byte-for-byte (cross-language golden fixture)', async () => {
  const payload = { schema_version: '1.0.0', a: '文化', n: [1, 2, 3] };
  assert.equal(canonicalJson(payload), '{"a":"文化","n":[1,2,3],"schema_version":"1.0.0"}');
  assert.equal(
    await canonicalSha256(payload),
    '893e9929704c727cbdf8c2899076ec2aeab289050bd246f72904602a6e77bd79',
  );
});

test('keys sort by UTF-16 code units, not code points', () => {
  const emoji = '\u{1F600}'; // D83D DE00
  const bang = '！'; // FF01
  assert.equal(canonicalJson({ [emoji]: 1, [bang]: 2 }), `{"${emoji}":1,"${bang}":2}`);
  assert.equal(canonicalJson({ b: 1, a: 2 }), '{"a":2,"b":1}');
});

test('floats and unsupported types are rejected', () => {
  assert.throws(() => canonicalJson({ cost: 1.5 }), (error: unknown) => error instanceof CanonicalJsonError);
  assert.throws(() => canonicalJson({ when: new Date(0) }), (error: unknown) => error instanceof CanonicalJsonError);
});

test('string escaping uses the shortest form', () => {
  assert.equal(canonicalJson({ k: 'a"b\\c\n' }), '{"k":"a\\"b\\\\c\\n"}');
  assert.equal(canonicalJson({ k: '\u0001' }), '{"k":"\\u0001"}');
});
