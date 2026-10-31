/**
 * Material → evidence panel.
 *
 * The creator uploads text, a PDF or a picture and presses one button; the
 * Evidence agent proposes the facts. Manual correction stays available (the
 * quotes are editable) but is no longer the only path, which the earlier version
 * wrongly forced on the user.
 */
import React, { useRef, useState } from 'react';

import { ApiError, type Claim, type SourceSummary } from '../lib/api.ts';
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
  const [sources, setSources] = useState<SourceSummary[]>([]);
  const [extracting, setExtracting] = useState(false);
  const [gaps, setGaps] = useState<string[]>([]);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const fileInput = useRef<HTMLInputElement>(null);
  const gate = gates(state);

  const refreshSources = async () => {
    if (!state.project) return;
    const listed = await client.listSources(state.project.id);
    setSources(listed);
    const ready = listed.find((source) => source.parse_status === 'ready');
    if (ready) {
      const spans = await client.listSpans(ready.source_id);
      dispatch({ type: 'material_parsed', sourceId: ready.source_id, spans });
    }
  };

  const uploadText = () =>
    run(async () => {
      if (!state.project) return;
      try {
        const source = await client.uploadText(state.project.id, { text, title: '材料一', license_note: license });
        const spans = await client.listSpans(source.source_id);
        dispatch({ type: 'material_parsed', sourceId: source.source_id, spans });
        await refreshSources();
      } catch (error) {
        if (error instanceof ApiError) {
          dispatch({ type: 'material_failed', code: error.code, message: error.message });
          return;
        }
        throw error;
      }
    });

  const uploadFile = (file: File) =>
    run(async () => {
      if (!state.project) return;
      try {
        const source = await client.uploadFile(state.project.id, file, license);
        if (source.parse_status === 'ready') {
          const spans = await client.listSpans(source.source_id);
          dispatch({ type: 'material_parsed', sourceId: source.source_id, spans });
        } else {
          dispatch({
            type: 'material_failed',
            code: source.error_code ?? 'PARSE_FAILED',
            message: '资料未能解析，请检查文件类型或内容。',
          });
        }
        await refreshSources();
      } catch (error) {
        if (error instanceof ApiError) {
          dispatch({ type: 'material_failed', code: error.code, message: error.message });
          return;
        }
        throw error;
      }
    });

  const freeze = () =>
    run(async () => {
      if (!state.project || !state.sourceId) return;
      const snapshot = await client.createSnapshot(state.project.id, [state.sourceId]);
      dispatch({ type: 'snapshot_created', snapshotId: snapshot.id });
    });

  const extract = () =>
    run(async () => {
      if (!state.project || !state.snapshotId) return;
      setExtracting(true);
      try {
        const result = await client.extractClaims(state.project.id, state.snapshotId);
        setGaps(result.gaps);
        dispatch({ type: 'claims_updated', claims: await client.listClaims(state.project.id) });
      } finally {
        setExtracting(false);
      }
    });

  const saveClaim = (claim: Claim) =>
    run(async () => {
      if (!state.project) return;
      const statement = (edits[claim.id] ?? claim.statement).trim();
      if (!statement || statement === claim.statement) return;
      // A correction is a new claim revision, never an in-place rewrite.
      await client.addClaims(state.project.id, [
        { statement, content_type: claim.content_type, evidence_span_ids: claim.evidence_span_ids },
      ]);
      dispatch({ type: 'claims_updated', claims: await client.listClaims(state.project.id) });
    });

  return (
    <Panel title="资料与证据" headingId="material-heading" index="零一">
      <Field label="正文（也可上传 PDF 或图片）">
        <textarea rows={5} value={text} onChange={(event) => setText(event.target.value)} />
      </Field>
      <Field label="授权说明">
        <input value={license} onChange={(event) => setLicense(event.target.value)} />
      </Field>

      <div className="row">
        <button onClick={uploadText} disabled={!state.project}>
          上传正文
        </button>
        <button
          onClick={() => fileInput.current?.click()}
          disabled={!state.project}
          title="支持文本 PDF、PNG、JPEG、WebP"
        >
          上传文件
        </button>
        <input
          ref={fileInput}
          type="file"
          accept=".txt,.md,.pdf,image/png,image/jpeg,image/webp"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void uploadFile(file);
            event.target.value = '';
          }}
        />
        <button onClick={freeze} disabled={!gate.canFreeze}>
          冻结证据快照
        </button>
      </div>
      {gate.reasons.length > 0 && <p className="hint">{gate.reasons.join(' · ')}</p>}

      {sources.length > 0 && (
        <ul className="source-list">
          {sources.map((source) => (
            <li key={source.source_id}>
              <span className="meta">{source.title ?? source.source_id.slice(0, 8)}</span>
              <span className={`pill ${source.parse_status === 'ready' ? 'pill-ok' : 'pill-bad'}`}>
                {source.parse_status}
              </span>
            </li>
          ))}
        </ul>
      )}

      <div className="row">
        <button className="primary" onClick={extract} disabled={!state.snapshotId || extracting}>
          {extracting ? '证据 Agent 正在抽取…' : '让证据 Agent 自动抽取事实'}
        </button>
        <span className="meta">
          <Count value={state.claims.length} /> 条事实
        </span>
      </div>

      {gaps.length > 0 && (
        <div className="gaps">
          <p className="xj-kicker">资料缺口</p>
          <ul>
            {gaps.map((gap, index) => (
              <li key={index}>{gap}</li>
            ))}
          </ul>
        </div>
      )}

      <ol className="claims">
        {state.claims.map((claim) => (
          <li key={`${claim.id}:${claim.revision}`}>
            <span className={`tag tag-${claim.content_type}`}>{claim.content_type}</span>
            <input
              aria-label="事实陈述（可直接修正）"
              value={edits[claim.id] ?? claim.statement}
              onChange={(event) => setEdits({ ...edits, [claim.id]: event.target.value })}
              onBlur={() => void saveClaim(claim)}
            />
          </li>
        ))}
      </ol>
    </Panel>
  );
}
