/* Generated from packages/contracts/experience-spec.schema.json — do not edit by hand. */
export type Text = string;
export type Uuid = string;
export type Id = string;
export type Claim = {
  id: Id;
  statement: Text;
  content_type: 'supported' | 'legend' | 'adaptation' | 'unconfirmed';
  evidence_span_ids: Uuid[];
  source_claim_id: Uuid;
  source_claim_revision: number;
};
export type Scene = {
  id: Id;
  title: Text;
  text: Text;
  content_type: 'supported' | 'legend' | 'adaptation' | 'unconfirmed';
  asset_ids: Id[];
  tasks: Task[];
  transitions: Transition[];
  claim_ids: Id[];
};
export type Task = Hotspot | Choice | Sequence;
export type Condition =
  | {
      all: Condition[];
    }
  | {
      any: Condition[];
    }
  | {
      not: Condition;
    }
  | {
      flag_equals: {
        id: Id;
        value: boolean;
      };
    };
export type ChoiceOption = {
  id: Id;
  label: Text;
  correct: boolean;
  feedback: Text;
  on_success: Effect[];
  target_scene?: Id;
};

export interface ExperienceSpec {
  schema_version: '1.0.0';
  runtime_version: '1.0.0';
  brief: {
    audience: Text;
    duration_minutes: number;
    learning_goals: Text[];
  };
  source_snapshot_id: Uuid;
  entry_scene: Id;
  flags: {
    id: Id;
    initial: false;
  }[];
  claims: Claim[];
  objectives: {
    id: Id;
    description: Text;
    claim_ids: Id[];
  }[];
  scenes: Scene[];
  completion: {
    scene_id: Id;
    required_flags: Id[];
  };
  asset_manifest: {
    id: Id;
    sha256: string;
    mime_type: 'image/png' | 'image/jpeg' | 'image/webp';
    license_note: Text;
  }[];
}
export interface Hotspot {
  id: Id;
  type: 'hotspot';
  label: Text;
  required: boolean;
  completion_flag: Id;
  objective_ids: Id[];
  claim_ids: Id[];
  requires: Condition;
  on_success: Effect[];
  feedback: Feedback;
  hints: Text[];
}
export interface Effect {
  set_flag: Id;
  value: true;
}
export interface Feedback {
  success: Text;
  failure: Text;
  claim_ids: Id[];
}
export interface Choice {
  id: Id;
  type: 'choice';
  label: Text;
  required: boolean;
  completion_flag: Id;
  objective_ids: Id[];
  claim_ids: Id[];
  requires: Condition;
  on_success: Effect[];
  feedback: Feedback;
  hints: Text[];
  options: ChoiceOption[];
}
export interface Sequence {
  id: Id;
  type: 'sequence';
  label: Text;
  required: boolean;
  completion_flag: Id;
  objective_ids: Id[];
  claim_ids: Id[];
  requires: Condition;
  on_success: Effect[];
  feedback: Feedback;
  hints: Text[];
  items: {
    id: Id;
    label: Text;
  }[];
  precedence: {
    before: Id;
    after: Id;
    claim_id: Id;
  }[];
}
export interface Transition {
  id: Id;
  label: Text;
  requires: Condition;
  target_scene: Id;
}
