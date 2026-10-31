/* Generated from packages/contracts/agent-protocol.schema.json — do not edit by hand. */
/**
 * Versioned structured handoff between the Coordinator and specialised agents (F10).
 */
export type AgentProtocol = Envelope | Result | Plan | PlanTask | Issue | Usage | Role;
export type Role =
  'coordinator' | 'evidence' | 'experience_designer' | 'experience_builder' | 'review' | 'repair' | 'guide';

export interface Envelope {
  protocol_version: '1.0.0';
  agent_id: string;
  task_id: string;
  parent_task_id: string | null;
  project_id: string;
  run_id: string;
  role: Role;
  profile_version: string;
  input_refs: string[];
  input_hash: string;
  allowed_tools: string[];
  budget_ref: string;
  fencing_token: number;
  objective: string;
}
export interface Result {
  protocol_version: '1.0.0';
  task_id: string;
  agent_id: string;
  role: Role;
  status: 'succeeded' | 'failed' | 'cancelled' | 'needs_input';
  artifact_refs: string[];
  citation_refs: string[];
  issues: Issue[];
  usage: Usage;
  handoff_to: Role[];
  reason_code: string | null;
}
export interface Issue {
  code: string;
  message: string;
  severity: 'error' | 'warning' | 'info';
  artifact_ref: string | null;
  claim_ids: string[];
}
export interface Usage {
  model_calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_status: 'actual' | 'estimated' | 'unknown';
  cost_micros: number | null;
  currency: string | null;
}
export interface Plan {
  protocol_version: '1.0.0';
  project_id: string;
  run_id: string;
  tasks: PlanTask[];
  notes: string;
  plan_hash: string;
}
export interface PlanTask {
  task_id: string;
  role: Role;
  objective: string;
  depends_on: string[];
  input_refs: string[];
  allowed_tools: string[];
  expected_output: string;
}
