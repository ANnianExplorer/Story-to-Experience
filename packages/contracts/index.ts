/**
 * Public entry point for the versioned contracts.
 *
 * Generated types come from the JSON Schemas in this package; this file only
 * gives stable, unambiguous names to the union branches so application code
 * never has to guess which branch of a `oneOf` it holds.
 */
export type { ExperienceSpec, Claim, Scene, Task, Condition, Effect, Feedback, Transition, ChoiceOption, Hotspot, Choice, Sequence } from './generated/experience-spec.ts';
export type {
  AgentProtocol,
  Envelope as AgentTaskEnvelope,
  Result as AgentResult,
  Plan as AgentPlan,
  PlanTask as AgentPlanTask,
  Issue as AgentIssue,
  Usage as AgentUsage,
  Role as AgentRole,
} from './generated/agent-protocol.ts';
export type {
  DialogueProfile as DialogueProfileContract,
  Profile as DialogueProfile,
  Turn as DialogueTurn,
  Citation as DialogueCitation,
  SuggestedAction as DialogueSuggestedAction,
  Action as DialogueAction,
} from './generated/dialogue-profile.ts';
