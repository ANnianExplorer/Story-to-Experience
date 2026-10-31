/**
 * Material → evidence panel: upload, inspect spans, record claims, freeze snapshot.
 *
 * The gates come from `lib/workbench-state.ts`; the UI never offers a button the
 * server would reject for a *business* reason (it can still fail technically).
 */
import React, { useState } from 'react';

import { ApiError, type Span } from '../lib/api.ts';
import { gates } from '../lib/workbench-state.ts';
import { client, type WorkbenchScope } from '../hooks/use-workbench.ts';
import { Count, Field, Panel } from './primitives.tsx';

const SAMPLE = `合成教学材料（非真实非遗工艺，仅用于演示）

工坊里的小铲用来翻松陶土。

翻松陶土之后要先阴干，再入窑。

入窑之前需要检查湿度。`;

export function MaterialPanel({ scope }: { scope: WorkbenchScope }) {
  const { state, dispatch, run } = scope;
  const [text, setText] = useState(SAMPLE);
  const [license, setLicense] = useState('合成教学样例，允许演示使用。');
  const [editing, setEditing] = useState<Record<string, string>>({});
  const gate = gates(state);

  const upload = () =>
    run(async () => {
      if (!state.project) return;
      try {
        const source = await client.uploadText(state.project.id, { text, title: '材料一', license_note: license });
        const spans = await client.listSpans(source.source_id);
        dispatch({ type: 'material_parsed', sourceId: source.source_id, spans });
      } catch (error) {
        if (error instanceof ApiError) {
          dispatch({ type: 'material_failed', code: error.code, message: error.message });
          return;
        }
        throw error;
      }
    });

  const addClaim = (span: Span) =>
    run(async () => {
      if (!state.project) return;
      const statement = (editing[span.id] ?? span.quote).trim();
      await client.addClaims(state.project.id, [
        { statement, content_type: 'supported', evidence_span_ids: [span.id] },
      ]);
      dispatch({ type: 'claims_updated', claims: await client.listClaims(state.project.id) });
    });

  const freeze = () =>
    run(async () => {
      if (!state.project || !state.sourceId) return;
      const snapshot = await client.createSnapshot(state.project.id, [state.sourceId]);
      dispatch({ type: 'snapshot_created', snapshotId: snapshot.id });
    });

  return (
    <Panel title="资料与证据" headingId="material-heading" index="零一">
      <Field label="正文">
        <textarea rows={6} value={text} onChange={(event) => setText(event.target.value)} />
      </Field>
      <Field label="授权说明">
        <input value={license} onChange={(event) => setLicense(event.target.value)} />
      </Field>
      <div className="row">
        <button onClick={upload} disabled={!state.project}>
          上传并解析
        </button>
        <button onClick={freeze} disabled={!gate.canFreeze}>
          冻结证据快照
        </button>
      </div>
      {gate.reasons.length > 0 && <p className="hint">{gate.reasons.join(' · ')}</p>}

      <h3>
        片段 <Count value={state.spans.length} />
      </h3>
      <ol className="spans">
        {state.spans.map((span) => (
          <li key={span.id}>
            <p className="quote">{span.quote}</p>
            <div className="row tight">
              <input
                aria-label="事实陈述"
                value={editing[span.id] ?? span.quote}
                onChange={(event) => setEditing({ ...editing, [span.id]: event.target.value })}
              />
              <button onClick={() => addClaim(span)}>记为事实</button>
            </div>
          </li>
        ))}
      </ol>

      <h3>
        事实 <Count value={state.claims.length} />
      </h3>
      <ul className="claims">
        {state.claims.map((claim) => (
          <li key={claim.id}>
            <span className={`tag tag-${claim.content_type}`}>{claim.content_type}</span>
            {claim.statement}
          </li>
        ))}
      </ul>
    </Panel>
  );
}
