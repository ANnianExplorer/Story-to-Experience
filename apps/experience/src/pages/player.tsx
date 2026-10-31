/**
 * Entry page: read the share token from the URL, fetch the frozen manifest,
 * open a participant session and a Guide conversation, then play.
 *
 * A token that is invalid, expired or revoked fails here with a plain message:
 * the page never falls back to a cached copy or an unsupported version.
 */
import React, { useEffect, useState } from 'react';

import type { ExperienceSpec } from '../../../../packages/contracts/index.ts';
import type { DialogueProfile } from '../../../../packages/contracts/index.ts';
import { GuidePanel } from '../components/guide-panel.tsx';
import { InkBackdrop } from '../components/ink-backdrop.tsx';
import { SceneView } from '../components/scene-view.tsx';
import { PlayerClient, PlayerError } from '../lib/player-api.ts';
import { currentScene, hintFor, openSession, reduceSession, type ActionInput, type PlayerSession } from '../lib/session.ts';

const client = new PlayerClient();

function tokenFromHash(): string | null {
  const hash = window.location.hash.replace(/^#/, '');
  const segments = hash.split('/').filter(Boolean);
  if (segments[0] === 'play' && segments[1]) return decodeURIComponent(segments[1]);
  return null;
}

export function PlayerPage() {
  const [session, setSession] = useState<PlayerSession | null>(null);
  const [profile, setProfile] = useState<DialogueProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [versionId, setVersionId] = useState<string | null>(null);
  const token = tokenFromHash();

  useEffect(() => {
    if (!token) {
      setError('缺少分享令牌。请使用创作者提供的完整链接。');
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const manifest = await client.manifest(token);
        const opened = await client.openSession(token);
        const spec = manifest.spec as unknown as Parameters<typeof openSession>[0];
        if (!cancelled) {
          setProfile(manifest.dialogue_profile);
          setVersionId(manifest.version_id);
          setSession(openSession(spec, opened.session_id, null));
        }
      } catch (caught) {
        if (!cancelled) {
          setError(
            caught instanceof PlayerError
              ? caught.code === 'SHARE_NOT_FOUND'
                ? '这个分享已失效或被撤销。'
                : caught.message
              : '无法加载体验，请检查网络后重试。',
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (error) {
    return (
      <div className="page">
        <h1>叙境</h1>
        <p role="alert" className="banner banner-error">{error}</p>
        <p className="meta">已下载的离线资料包不受影响；在线体验需要有效的分享链接。</p>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="page">
        <p>正在打开体验…</p>
      </div>
    );
  }

  const scene = currentScene(session);
  const replay = () => setSession((current) => (current ? reduceSession(current, { type: 'replay' }) : current));

  return (
    <div className="player">
      <InkBackdrop seed={session.spec.scenes.findIndex((item) => item.id === session.state.scene_id) + 1} />
      <header className="player-head">
        <p className="brand-line">叙境 · 文化体验</p>
        <p className="meta">固定版本 {versionId?.slice(0, 8)} · 动画与出处不影响任务判定</p>
      </header>
      <main className="player-grid">
        <SceneView
          session={session}
          hint={hintFor(session)}
          onHint={() => setSession((current) => (current ? reduceSession(current, { type: 'hint', level: 3 }) : current))}
          onReplay={replay}
          onAction={(input: ActionInput) =>
            setSession((current) => (current ? reduceSession(current, { type: 'action', input }) : current))
          }
        />
        <GuidePanel
          client={client}
          session={session}
          profile={profile}
          onNavigate={(sceneId) => {
            const target: ActionInput | null = scene?.transitions.find((t) => t.target_scene === sceneId)
              ? { kind: 'transition', scene_id: session.state.scene_id, transition_id: scene.transitions.find((t) => t.target_scene === sceneId)!.id }
              : null;
            if (target) setSession((current) => (current ? reduceSession(current, { type: 'action', input: target }) : current));
          }}
          onOpenConversation={(conversationId) =>
            setSession((current) => (current ? reduceSession(current, { type: 'guide_opened', conversationId }) : current))
          }
        />
      </main>
      <footer className="player-foot">
        <p className="meta">
          角色对白为改编创作，不是历史原话；事实陈述可在场景内展开出处核对。
        </p>
      </footer>
    </div>
  );
}
