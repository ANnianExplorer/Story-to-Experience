/**
 * Live agent progress for a generation run.
 *
 * Shows the plan and each delegated sub-task with its real state, the tool
 * whitelist it ran under and its token usage. States come from the server; this
 * component never invents progress or a percentage.
 */
import React from 'react';

import type { AgentTaskView, RunSnapshot } from '../lib/api.ts';
import { formatCost } from '../lib/workbench-state.ts';
import { StatusPill } from './primitives.tsx';

const ROLE_LABEL: Record<string, string> = {
  coordinator: '统筹 · 计划',
  evidence: '证据 · 抽取与检索',
  experience_designer: '设计 · 场景与机制',
  experience_builder: '构建 · 规格与文案',
  review: '审校 · 表述与来源',
  repair: '修复 · 局部补丁',
};

const ROLE_ORDER = ['coordinator', 'evidence', 'experience_designer', 'experience_builder', 'review', 'repair'];

const STATUS_LABEL: Record<string, string> = {
  succeeded: '已完成',
  failed: '失败',
  running: '执行中',
  waiting: '等待中',
  pending: '未开始',
  not_needed: '未触发',
  cancelled: '已取消',
};

function toneFor(status: string): 'neutral' | 'ok' | 'warn' | 'bad' {
  if (status === 'succeeded') return 'ok';
  if (status === 'failed') return 'bad';
  if (status === 'running') return 'warn';
  return 'neutral';
}

export interface AgentTimelineProps {
  run: RunSnapshot | null;
  tasks: AgentTaskView[];
  planNotes: string | null;
}

export function AgentTimeline({ run, tasks, planNotes }: AgentTimelineProps) {
  const byRole = new Map<string, AgentTaskView>();
  for (const task of tasks) byRole.set(task.role, task);
  const runSucceeded = run?.status === 'succeeded';
  const runTerminal = run?.status === 'succeeded' || run?.status === 'failed' || run?.status === 'cancelled';

  const ordered = [
    ...ROLE_ORDER.filter((role) => byRole.has(role) || run !== null),
    ...tasks.map((task) => task.role).filter((role) => !ROLE_ORDER.includes(role)),
  ];
  const unique = [...new Set(ordered)];

  return (
    <div className="timeline">
      <div className="timeline-meta">
        <span className="xj-kicker">执行轨迹</span>
        {run ? (
          <span className="timeline-stats">
            <StatusPill tone={run.status === 'succeeded' ? 'ok' : run.status === 'failed' ? 'bad' : 'warn'}>
              {run.status}
            </StatusPill>
            <span className="meta">{formatCost(run.budget)}</span>
          </span>
        ) : (
          <span className="meta">尚未提交</span>
        )}
      </div>

      {planNotes && <p className="timeline-plan">{planNotes}</p>}

      <ol className="timeline-list">
        {unique.map((role) => {
          const task = byRole.get(role);
          // The Coordinator is recorded in `agent_plans`, not as a task row, so a
          // successful run with a plan means it ran. Repair only runs when the
          // first validation fails, so "not needed" must not look like "pending".
          let derived = 'pending';
          if (task) {
            derived = task.status;
          } else if (role === 'coordinator') {
            derived = planNotes !== null || runSucceeded ? 'succeeded' : runTerminal ? 'failed' : 'waiting';
          } else if (role === 'repair') {
            derived = runTerminal ? 'not_needed' : 'pending';
          } else if (runTerminal) {
            derived = runSucceeded ? 'succeeded' : 'failed';
          } else if (run) {
            derived = 'waiting';
          }
          const status = derived;
          return (
            <li key={role} className={`timeline-step timeline-${status}`}>
              <span className="timeline-node" aria-hidden="true" />
              <div className="timeline-body">
                <div className="timeline-head">
                  <strong>{ROLE_LABEL[role] ?? role}</strong>
                  <StatusPill tone={toneFor(status)}>{STATUS_LABEL[status] ?? status}</StatusPill>
                </div>
                {task ? (
                  <>
                    <p>{task.envelope.objective}</p>
                    <p className="meta">
                      工具 {task.envelope.allowed_tools.length} 项 · 调用 {task.usage.model_calls ?? 0} 次 ·{' '}
                      {task.usage.input_tokens ?? 0}→{task.usage.output_tokens ?? 0} tokens ·{' '}
                      {task.usage.cost_status ?? 'unknown'}
                    </p>
                    {!!task.result?.issues?.length && (
                      <p className="meta timeline-issues">{task.result.issues.length} 条审校问题</p>
                    )}
                  </>
                ) : (
                  <p className="meta">
                    {status === 'not_needed' ? '首轮校验通过，无需修复' : status === 'waiting' ? '等待前序子任务' : '未开始'}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
