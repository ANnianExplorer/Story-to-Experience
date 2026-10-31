/**
 * Player session state, derived from the frozen share manifest.
 *
 * The engine (packages/engine) owns all task logic. This module only tracks
 * what the participant has seen and which scene is current, plus the Guide
 * conversation that is bound to the *same* frozen version.
 */
import {
  applyAction,
  initialState,
  isCompleted,
  replayState,
  type ActionInput,
  type ExperienceSpecModel,
  type PlayerState,
} from '../../../../packages/engine/src/engine.ts';

export interface PlayerSession {
  spec: ExperienceSpecModel;
  state: PlayerState;
  guideConversationId: string | null;
  experienceSessionId: string | null;
  hintLevel: number;
  lastFeedback: { text: string; code: string } | null;
}

export type PlayerEvent =
  | { type: 'opened'; spec: ExperienceSpecModel; experienceSessionId: string; guideConversationId: string | null }
  | { type: 'action'; input: ActionInput }
  | { type: 'guide_opened'; conversationId: string }
  | { type: 'hint'; level: number }
  | { type: 'replay' };

export function openSession(spec: ExperienceSpecModel, experienceSessionId: string, guideConversationId: string | null): PlayerSession {
  return {
    spec,
    state: initialState(spec),
    guideConversationId,
    experienceSessionId,
    hintLevel: 0,
    lastFeedback: null,
  };
}

/**
 * Apply one participant action through the shared engine.
 * Invalid input and wrong answers never change logical state.
 */
export function dispatchAction(session: PlayerSession, input: ActionInput): PlayerSession {
  const result = applyAction(session.spec, session.state, input);
  return {
    ...session,
    state: result.next_state,
    lastFeedback: { text: result.feedback, code: result.result_code },
  };
}

export function reduceSession(session: PlayerSession, event: PlayerEvent): PlayerSession {
  switch (event.type) {
    case 'action':
      return dispatchAction(session, event.input);
    case 'guide_opened':
      return { ...session, guideConversationId: event.conversationId };
    case 'hint':
      return { ...session, hintLevel: Math.min(session.hintLevel + 1, event.level) };
    case 'replay':
      return {
        ...session,
        state: replayState(session.spec),
        hintLevel: 0,
        lastFeedback: null,
      };
    case 'opened':
      return openSession(event.spec, event.experienceSessionId, event.guideConversationId);
    default:
      return session;
  }
}

export function currentScene(session: PlayerSession) {
  return session.spec.scenes.find((scene) => scene.id === session.state.scene_id) ?? null;
}

export function sessionCompleted(session: PlayerSession): boolean {
  return isCompleted(session.spec, session.state);
}

/** Hint text is derived from the frozen spec; it never unlocks anything. */
export function hintFor(session: PlayerSession): string | null {
  const scene = currentScene(session);
  if (!scene) return null;
  const withHints = scene.tasks.find((task) => task.hints.length > 0);
  if (!withHints) return null;
  const index = Math.min(session.hintLevel, withHints.hints.length - 1);
  return withHints.hints[index] ?? null;
}

export type { ActionInput, PlayerState };
