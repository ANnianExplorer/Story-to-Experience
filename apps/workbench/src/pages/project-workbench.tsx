/**
 * Project workbench: the three-column creator surface.
 *
 * Reaching this page loads the *server* state (project, claims, versions); the
 * page never assumes a previous in-memory session still exists, so a reload
 * shows the truth rather than a stale preview.
 */
import React, { useEffect } from 'react';
import { AnimatePresence, MotionConfig, m, useReducedMotion } from 'motion/react';

import tokens from '../../../../packages/ui/tokens.json';
import { ChatPanel } from '../components/chat-panel.tsx';
import { MaterialPanel } from '../components/material-panel.tsx';
import { RunPanel } from '../components/run-panel.tsx';
import { VersionPanel } from '../components/version-panel.tsx';
import { StatusPill } from '../components/primitives.tsx';
import { client, type WorkbenchScope } from '../hooks/use-workbench.ts';
import { STAGE_LABEL } from '../lib/workbench-state.ts';

const ease = tokens.motion.ease as [number, number, number, number];
const panelMs = tokens.motion.duration_ms.panel;

export function ProjectPage({ scope, projectId }: { scope: WorkbenchScope; projectId: string }) {
  const { state, dispatch, run } = scope;
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    void run(async () => {
      const project = await client.getProject(projectId);
      dispatch({ type: 'project_created', project });
      const claims = await client.listClaims(projectId);
      if (claims.length > 0) dispatch({ type: 'claims_updated', claims });
      const versions = await client.listVersions(projectId);
      if (versions.length > 0) {
        const head = versions[0];
        if (head) dispatch({ type: 'candidate_ready', versions, selectedVersionId: head.id });
      }
    });
  }, [dispatch, projectId, run]);

  const transition = { duration: reduceMotion ? 0 : panelMs / 1000, ease };
  const delayed = (index: number) => ({
    ...transition,
    delay: reduceMotion ? 0 : index * 0.04,
  });

  return (
    <>
      <div className="project-head">
        <h2>{state.project?.name ?? '正在加载项目…'}</h2>
        <StatusPill tone="neutral">阶段：{STAGE_LABEL[state.stage]}</StatusPill>
        {state.project && state.project.stable_version_id && <StatusPill tone="ok">已有稳定版</StatusPill>}
        {state.error && (
          <p className="banner banner-error" role="alert">
            {state.error.message} <code>{state.error.code}</code>
          </p>
        )}
      </div>
      <main className="grid">
        <MotionConfig reducedMotion={reduceMotion ? 'always' : 'user'}>
          <AnimatePresence initial={false}>
            <m.div
              key="material"
              className="column"
              initial={{ opacity: 0, y: reduceMotion ? 0 : 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={delayed(0)}
            >
              <MaterialPanel scope={scope} />
            </m.div>
            <m.div
              key="run"
              className="column"
              initial={{ opacity: 0, y: reduceMotion ? 0 : 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={delayed(1)}
            >
              <RunPanel scope={scope} />
              <ChatPanel scope={scope} />
            </m.div>
            <m.div
              key="version"
              className="column"
              initial={{ opacity: 0, y: reduceMotion ? 0 : 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={delayed(2)}
            >
              <VersionPanel scope={scope} />
            </m.div>
          </AnimatePresence>
        </MotionConfig>
      </main>
    </>
  );
}
