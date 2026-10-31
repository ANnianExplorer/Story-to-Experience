/**
 * Guide panel: ask questions inside the current scene and show citations.
 *
 * The conversation is opened against the participant's *experience session*, so
 * it is always bound to this frozen version. Suggested actions are rendered as
 * buttons, but they only ever propose a navigation/hint — the engine still owns
 * task state.
 */
import React, { useState } from 'react';

import { guideAnswer, type Citation, type PlayerClient } from '../lib/player-api.ts';
import type { PlayerSession } from '../lib/session.ts';
import type { DialogueProfile } from '../../../../packages/contracts/index.ts';

interface Message {
  role: 'user' | 'assistant';
  text: string;
  citations?: Citation[];
  answerability?: string;
  pending?: boolean;
}

export interface GuidePanelProps {
  client: PlayerClient;
  session: PlayerSession;
  profile: DialogueProfile | null;
  onOpenConversation: (conversationId: string) => void;
  onNavigate: (sceneId: string) => void;
}

export function GuidePanel({ client, session, profile, onOpenConversation, onNavigate }: GuidePanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(session.guideConversationId);

  const ensureConversation = async (): Promise<string | null> => {
    if (conversationId) return conversationId;
    if (!session.experienceSessionId) return null;
    const created = await client.openGuideConversation(session.experienceSessionId);
    setConversationId(created.conversation_id);
    onOpenConversation(created.conversation_id);
    return created.conversation_id;
  };

  const send = async () => {
    const text = draft.trim();
    if (!text || busy) return;
    setDraft('');
    setMessages((current) => [...current, { role: 'user', text }, { role: 'assistant', text: '正在检索本版本的公开资料…', pending: true }]);
    setBusy(true);
    try {
      const id = await ensureConversation();
      if (!id) return;
      const turn = await client.submitTurn(id, crypto.randomUUID(), text);
      const result = await client.runTurn(turn.turn_id);
      const answer = guideAnswer(result);
      setMessages((current) => {
        const next = [...current];
        next.pop();
        if (!answer) {
          next.push({ role: 'assistant', text: '本轮没有产生完整回答（可能被取消或失败），不展示部分文本。' });
          return next;
        }
        next.push({ role: 'assistant', text: answer.text, citations: answer.citations, answerability: answer.answerability });
        return next;
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="guide" aria-labelledby="guide-heading">
      <h2 id="guide-heading">问问导览</h2>
      {profile && (
        <p className="adaptation">
          {profile.persona.name}是改编角色，对白为创作，不是历史原话。
        </p>
      )}
      <div className="messages" role="log" aria-live="polite">
        {messages.map((message, index) => (
          <article key={index} className={`message message-${message.role}`}>
            <p>{message.text}</p>
            {message.citations && message.citations.length > 0 && (
              <ul className="citations">
                {message.citations.map((citation) => (
                  <li key={citation.span_id}>
                    <blockquote>{citation.quote}</blockquote>
                    <span className="meta">{citation.label}</span>
                  </li>
                ))}
              </ul>
            )}
            {message.answerability && message.answerability !== 'answered' && (
              <span className={`pill ${message.answerability === 'refused' ? 'pill-bad' : 'pill-warn'}`}>
                {message.answerability === 'unknown' ? '资料不足' : message.answerability === 'partial' ? '部分有据' : '已拒绝'}
              </span>
            )}
          </article>
        ))}
      </div>
      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <textarea
          rows={2}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="例如：为什么这一步必须排在后面？"
          disabled={busy}
        />
        <button type="submit" className="primary" disabled={busy || !draft.trim()}>
          提问
        </button>
      </form>
      {session.lastFeedback && session.lastFeedback.code === 'OK' && session.state.scene_id === session.spec.completion.scene_id && (
        <p className="hint">
          已完成。你可以
          <button className="link" onClick={() => onNavigate(session.spec.entry_scene)}>
            重新体验
          </button>
          。
        </p>
      )}
    </section>
  );
}
