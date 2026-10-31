/* Generated from packages/contracts/dialogue-profile.schema.json — do not edit by hand. */
/**
 * Versioned companion config for AI guide / character conversation (F11). Published alongside, not inside, ExperienceSpec 1.0.
 */
export type DialogueProfile = Profile | Turn | Citation | SuggestedAction | Action;
export type Action = 'open_source_card' | 'highlight_claim' | 'suggest_hint' | 'navigate_scene' | 'replay_scene';

export interface Profile {
  id: string;
  protocol_version: '1.0.0';
  profile_version: string;
  persona: {
    name: string;
    role: string;
  };
  adaptation_note: string;
  source_scope: string[];
  objective_ids: string[];
  hint_policy: 'none' | 'gentle' | 'progressive';
  max_hint_level: number;
  allowed_actions: Action[];
  model_policy_ref: string;
}
export interface Turn {
  id: string;
  session_id: string;
  client_turn_id: string;
  sequence: number;
  status: 'queued' | 'streaming' | 'succeeded' | 'failed' | 'cancelled';
  user_message: string;
  partial_text: string;
  final_text: string | null;
  answerability: 'answered' | 'partial' | 'unknown' | 'refused' | null;
  citations: Citation[];
  suggested_actions: SuggestedAction[];
  cost_status: 'actual' | 'estimated' | 'unknown';
  cost_micros: number | null;
}
export interface Citation {
  span_id: string;
  source_id: string;
  label: string;
  quote: string;
  start_cp: number;
  end_cp: number;
  claim_ids: string[];
}
export interface SuggestedAction {
  kind: Action;
  label: string;
  scene_id: string | null;
  claim_id: string | null;
  level: number | null;
}
