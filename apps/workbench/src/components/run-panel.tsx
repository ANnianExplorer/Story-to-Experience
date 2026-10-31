/**
 * Generation panel: submit, poll the run, show the real agent trace.
 *
 * Polling is the development transport; the SSE endpoint is used when the run
 * is long. Neither path invents progress: every row comes from the server.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';

import type { AgentTaskView, RunSnapshot } from '../lib/api.ts';
import { formatCost, gates } from '../lib/workbench-state.ts';
import { client, type WorkbenchScope } from '../hooks/use-workbench.ts';
import { Count, Field, Panel, StatusPill } from './primitives.tsx';

function queuedSnapshot(runId: string): RunSnapshot {
  return {
    id: runId,
    status: 'queued',
    stage: 'plan',
    attempt: 1,
    last_sequence: 0,
    budget: { max_calls: 12, calls_reserved: 0, calls_settled: 0, repair_rounds: 0 },
    error_code: null,
  };
}

export function RunPanel({ scope }: { scope: WorkbenchScope }) {
  const { state, dispatch, run } = scope;
  const [instruction, setInstruction] = useState('给五年级使用，六分钟，保留出处，先做一个可试玩的候选。');
  const gate = gates(state);
  const pollRef = useRef<number | null>(null);

  const poll = useCallback(
    async (runId: string) => {
      const snapshot = await client.getRun(runId);
      dispatch({ type: 'run_updated', run: snapshot });
      const trace = await client.listAgentTasks(runId);
      dispatch({ type: 'agent_tasks', tasks: trace.tasks });
      if (snapshot.status === 'succeeded' && state.project) {
        const versions = await client.listVersions(state.project.id);
        const head = versions[0];
        if (head) dispatch({ type: 'candidate_ready', versions, selectedVersionId: head.id });
      }
      if (['queued', 'running', 'waiting_input'].includes(snapshot.status)) {
        pollRef.current = window.setTimeout(() => void poll(runId), 1500);
      }
    },
    [dispatch, state.project],
  );

  useEffect(
    () => () => {
      if (pollRef.current) window.clearTimeout(pollRef.current);
    },
    [],
  );

  const start = () =>
    run(async () => {
      if (!state.project || !state.snapshotId) return;
      const submitted = await client.submitRun(
        state.project.id,
        {
          snapshotId: state.snapshotId,
          briefRevision: state.project.brief_revision,
          instruction,
          autoContinue: true,
        },
        crypto.randomUUID(),
      );
      dispatch({ type: 'run_queued', run: queuedSnapshot(submitted.run_id) });
      await poll(submitted.run_id);
    });

  const cancel = () =>
    run(async () => {
      if (!state.run) return;
      const snapshot = await client.cancelRun(state.run.id);
      dispatch({ type: 'run_updated', run: { ...state.run, status: snapshot.status } });
    });

  return (
    <Panel title="生成与执行轨迹" headingId="run-heading">
      <Field label="创作要求（自然语言）">
        <textarea rows={3} value={instruction} onChange={(event) => setInstruction(event.target.value)} />
      </Field>
      <div className="row">
        <button className="primary" onClick={start} disabled={!gate.canGenerate}>
          开始生成
        </button>
        <button
          onClick={cancel}
          disabled={!state.run || !['queued', 'running', 'waiting_input'].includes(state.run.status)}
        >
          取消
        </button>
      </div>
      {state.run && (
        <dl className="run-meta">
          <div>
            <dt>状态</dt>
            <dd>{state.run.status}</dd>
          </div>
          <div>
            <dt>阶段</dt>
            <dd>{state.run.stage}</dd>
          </div>
          <div>
            <dt>预算</dt>
            <dd>{formatCost(state.run.budget)}</dd>
          </div>
          {state.run.error_code && (
            <div className="error">
              <dt>错误</dt>
              <dd>{state.run.error_code}</dd>
            </div>
          )}
        </dl>
      )}
      <h3>
        Agent 子任务 <Count value={state.agentTasks.length} />
      </h3>
      <ol className="trace">
        {state.agentTasks.map((task: AgentTaskView) => (
          <li key={task.task_id}>
            <div className="trace-head">
              <strong>{task.role}</strong>
              <StatusPill tone={task.status === 'succeeded' ? 'ok' : task.status === 'failed' ? 'bad' : 'neutral'}>
                {task.status}
              </StatusPill>
            </div>
            <p>{task.envelope.objective}</p>
            <p className="meta">
              工具：{task.envelope.allowed_tools.join('、')} · 调用 {task.usage.model_calls ?? 0} 次 ·{' '}
              {task.usage.cost_status ?? 'unknown'}
            </p>
          </li>
        ))}
      </ol>
    </Panel>
  );
}
