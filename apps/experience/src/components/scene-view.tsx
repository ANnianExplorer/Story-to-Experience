/**
 * Scene renderer: text, the three mechanics, transitions and the source card.
 *
 * Every action goes through the shared engine (`dispatchAction`), so a wrong
 * answer or a locked transition cannot change state. Ordering offers up/down
 * buttons as a non-drag alternative (F04-R04).
 */
import React, { useMemo, useState } from 'react';

import type { ActionInput, PlayerSession } from '../lib/session.ts';

export interface SceneViewProps {
  session: PlayerSession;
  onAction: (input: ActionInput) => void;
  onHint: () => void;
  hint: string | null;
  onReplay: () => void;
}

export function SceneView({ session, onAction, onHint, hint, onReplay }: SceneViewProps) {
  const scene = session.spec.scenes.find((item) => item.id === session.state.scene_id);
  const [order, setOrder] = useState<string[] | null>(null);
  const [showSources, setShowSources] = useState(false);
  const claimsById = useMemo(() => new Map(session.spec.claims.map((claim) => [claim.id, claim])), [session.spec.claims]);

  if (!scene) {
    return (
      <section className="scene" role="alert">
        <p>体验数据不完整，无法继续。请联系创作者重新分享。</p>
      </section>
    );
  }

  const isCompletion = scene.id === session.spec.completion.scene_id;

  const move = (index: number, direction: -1 | 1) => {
    const sequenceTask = scene.tasks.find((task) => task.type === 'sequence');
    if (!sequenceTask || sequenceTask.type !== 'sequence') return;
    const current = order ?? sequenceTask.items.map((item) => item.id);
    const target = index + direction;
    if (target < 0 || target >= current.length) return;
    const next = [...current];
    const a = next[index];
    const b = next[target];
    if (a === undefined || b === undefined) return;
    next[index] = b;
    next[target] = a;
    setOrder(next);
  };

  return (
    <section className="scene" aria-labelledby="scene-title">
      <p className="chapter">{scene.content_type === 'adaptation' ? '改编场景' : scene.content_type === 'legend' ? '传说' : '资料场景'}</p>
      <h2 id="scene-title">{scene.title}</h2>
      <p className="scene-text">{scene.text}</p>

      {scene.tasks.map((task) => {
        const done = session.state.flags[task.completion_flag] === true;
        return (
          <div key={task.id} className={`task ${done ? 'task-done' : ''}`}>
            <h3>{task.label}</h3>
            {task.type === 'hotspot' && (
              <button
                onClick={() => onAction({ kind: 'task', scene_id: scene.id, task_id: task.id })}
                disabled={done}
              >
                {done ? '已记录' : '观察这里'}
              </button>
            )}
            {task.type === 'choice' &&
              task.options.map((option) => (
                <button
                  key={option.id}
                  className="choice"
                  disabled={done}
                  onClick={() =>
                    onAction({ kind: 'task', scene_id: scene.id, task_id: task.id, option_id: option.id })
                  }
                >
                  {option.label}
                </button>
              ))}
            {task.type === 'sequence' && (
              <ol className="order-list">
                {(order ?? task.items.map((item) => item.id)).map((itemId, index) => {
                  const item = task.items.find((candidate) => candidate.id === itemId);
                  return (
                    <li key={itemId}>
                      <span>{item?.label ?? itemId}</span>
                      <span className="order-controls">
                        <button aria-label="上移" onClick={() => move(index, -1)} disabled={done || index === 0}>
                          ↑
                        </button>
                        <button
                          aria-label="下移"
                          onClick={() => move(index, 1)}
                          disabled={done || index === (order ?? task.items).length - 1}
                        >
                          ↓
                        </button>
                      </span>
                    </li>
                  );
                })}
              </ol>
            )}
            {task.type === 'sequence' && (
              <button
                className="primary"
                disabled={done}
                onClick={() =>
                  onAction({
                    kind: 'task',
                    scene_id: scene.id,
                    task_id: task.id,
                    order: order ?? task.items.map((item) => item.id),
                  })
                }
              >
                提交顺序
              </button>
            )}
            {task.hints.length > 0 && !done && (
              <button className="link" onClick={onHint}>
                给一点提示
              </button>
            )}
          </div>
        );
      })}

      {hint && <p className="hint-box" role="status">{hint}</p>}
      {session.lastFeedback && session.lastFeedback.text && (
        <p className={`feedback feedback-${session.lastFeedback.code === 'OK' ? 'ok' : 'bad'}`} role="status">
          {session.lastFeedback.text}
        </p>
      )}

      <div className="row">
        {scene.transitions.map((transition) => (
          <button
            key={transition.id}
            className="primary"
            onClick={() => onAction({ kind: 'transition', scene_id: scene.id, transition_id: transition.id })}
          >
            {transition.label}
          </button>
        ))}
        <button onClick={() => setShowSources((value) => !value)} aria-expanded={showSources}>
          {showSources ? '收起出处' : '查看出处'}
        </button>
      </div>

      {showSources && (
        <aside className="sources">
          {scene.claim_ids.length === 0 && <p className="hint">本场景没有绑定事实陈述。</p>}
          <ul>
            {scene.claim_ids.map((claimId) => {
              const claim = claimsById.get(claimId);
              if (!claim) return null;
              return (
                <li key={claimId}>
                  <span className={`tag tag-${claim.content_type}`}>{claim.content_type}</span>
                  {claim.statement}
                </li>
              );
            })}
          </ul>
          <p className="meta">出处开关只影响展示，不会改变任务状态。</p>
        </aside>
      )}

      {isCompletion && (
        <button className="primary" onClick={onReplay}>
          再体验一次
        </button>
      )}
    </section>
  );
}
