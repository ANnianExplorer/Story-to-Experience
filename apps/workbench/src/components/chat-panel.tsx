/**
 * Creator co-creation chat: submits turns, renders only completed answers.
 *
 * Citation rendering is mandatory: an answer without citations is labelled as
 * partial by the server, and the UI shows that label rather than implying the
 * claim is proven.
 */
import React, { useCallback, useState } from 'react';

import { finalMessageFromTurn, type Citation } from '../lib/api.ts';
import type { WorkbenchScope } from '../hooks/use-workbench.ts';
import { client } from '../hooks/use-workbench.ts';
import { Panel, StatusPill } from './primitives.tsx';

interface Message {
  role: 'user' | 'assistant';
  text: string;
  citations?: Citation[];
  answerability?: string;
  pending?: boolean;
}

export function ChatPanel({ scope }: { scope: WorkbenchScope }) {
  const { state, run } = scope;
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const ensureConversation = useCallback(async (): Promise<string | null> => {
    if (conversationId) return conversationId;
    if (!state.project) return null;
    const created = await client.createCreatorConversation(state.project.id, state.selectedVersionId ?? undefined);
    setConversationId(created.conversation_id);
    return created.conversation_id;
  }, [conversationId, state.project, state.selectedVersionId]);

  const send = () =>
    run(async () => {
      const text = draft.trim();
      if (!text) return;
      setDraft('');
      setMessages((current) => [
        ...current,
        { role: 'user', text },
        { role: 'assistant', text: '正在检索证据并组织回答…', pending: true },
      ]);
      setBusy(true);
      try {
        const id = await ensureConversation();
        if (!id) return;
        const turn = await client.submitTurn(id, { clientTurnId: crypto.randomUUID(), message: text });
        const result = await client.runTurn(turn.turn_id);
        const final = finalMessageFromTurn(result);
        setMessages((current) => {
          const next = [...current];
          next.pop();
          if (!final) {
            next.push({
              role: 'assistant',
              text: '本轮没有产生可用的完整回答（可能被取消或失败），不展示部分文本。',
            });
            return next;
          }
          next.push({ role: 'assistant', text: final.text, citations: final.citations, answerability: final.answerability });
          return next;
        });
      } finally {
        setBusy(false);
      }
    });

  return (
    <Panel title="创作共创" headingId="chat-heading">
      <p className="hint">AI 可以解释、检索与提计划，但不会替你发布；所有修改仍走受控用例。</p>
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
              <StatusPill tone={message.answerability === 'refused' ? 'bad' : 'warn'}>{message.answerability}</StatusPill>
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
          placeholder="例如：为什么 A 要排在 C 前面？如果没有依据请直接说明。"
          disabled={!state.project || busy}
        />
        <button type="submit" className="primary" disabled={!state.project || busy || !draft.trim()}>
          发送
        </button>
      </form>
    </Panel>
  );
}
