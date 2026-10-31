/**
 * Version list, human review and stable promotion.
 *
 * The UI states plainly that a stable version is not a public release: sharing
 * still requires technical reports to match the content hash.
 */
import React, { useState } from 'react';

import { client, type WorkbenchScope } from '../hooks/use-workbench.ts';
import { Field, Panel, StatusPill } from './primitives.tsx';

export function VersionPanel({ scope }: { scope: WorkbenchScope }) {
  const { state, dispatch, run } = scope;
  const [notes, setNotes] = useState('');
  const selected = state.versions.find((version) => version.id === state.selectedVersionId) ?? null;

  const approve = () =>
    run(async () => {
      if (!state.project || !selected) return;
      dispatch({ type: 'review_submitted' });
      // Cover exactly the claims this *version* binds. Project-level claims
      // include drafts that never entered the frozen snapshot, and a review
      // naming them would be rejected (REVIEW_COVERAGE_UNKNOWN).
      const version = await client.getVersion(selected.id);
      const claims = (version.spec as { claims?: { id: string }[] }).claims ?? [];
      await client.submitReview(selected.id, {
        decision: 'approved',
        notes: notes || '内容与来源核对通过。',
        coverage_claim_ids: claims.map((claim) => claim.id),
        expected_semantic_hash: selected.semantic_hash,
      });
      await client.promoteStable(state.project.id, selected.id);
      dispatch({ type: 'stable', project: await client.getProject(state.project.id) });
    });

  return (
    <Panel title="版本与审核" headingId="version-heading" index="零四">
      {state.versions.length === 0 && <p className="hint">尚未生成候选。完成一次生成后在此查看版本。</p>}
      <ul className="versions">
        {state.versions.map((version) => (
          <li key={version.id} className={version.id === state.selectedVersionId ? 'selected' : ''}>
            <button
              className="link"
              onClick={() => dispatch({ type: 'candidate_ready', versions: state.versions, selectedVersionId: version.id })}
            >
              {version.id.slice(0, 8)}
            </button>
            <span className="meta">语义 {version.semantic_hash.slice(0, 10)}…</span>
            {state.project?.stable_version_id === version.id && <StatusPill tone="ok">稳定版</StatusPill>}
          </li>
        ))}
      </ul>
      {selected && (
        <>
          <Field label="审核说明">
            <textarea
              rows={2}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="记录核对范围与结论"
            />
          </Field>
          <button
            onClick={approve}
            disabled={state.stage === 'stable' && state.project?.stable_version_id === selected.id}
          >
            提交人工审核并设为稳定版
          </button>
          <p className="hint">正式分享还需要技术检查通过；稳定版不等于已经对外发布。</p>
        </>
      )}
    </Panel>
  );
}
