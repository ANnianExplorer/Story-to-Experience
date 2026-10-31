/**
 * Hand-built fixture. Expectations in the tests are written by hand from the
 * material (A<C, B<C ⇒ ABC, BAC valid; ACB/BCA/CAB/CBA invalid) rather than
 * produced by the implementation under test.
 */
import type { ExperienceSpecModel } from '../src/engine.ts';

export const SPAN_A = '30000000-0000-4000-8000-000000000001';
export const SPAN_B = '30000000-0000-4000-8000-000000000002';
export const SPAN_C = '30000000-0000-4000-8000-000000000003';

export function workshopSpec(): ExperienceSpecModel {
  // Contract: no condition is expressed as a declared always-false flag compared
  // to false, never as an empty `all` (experience-spec §条件与效果).
  const noRequires = { flag_equals: { id: 'never', value: false } } as const;
  return {
    schema_version: '1.0.0',
    runtime_version: '1.0.0',
    brief: { audience: '合成教学样例', duration_minutes: 5, learning_goals: ['识别前置步骤'] },
    source_snapshot_id: '10000000-0000-4000-8000-000000000001',
    entry_scene: 'entry',
    flags: [
      { id: 'clue_seen', initial: false },
      { id: 'choice_done', initial: false },
      { id: 'sequence_done', initial: false },
      { id: 'never', initial: false },
      { id: 'bonus', initial: false },
    ],
    claims: [
      {
        id: 'claim_A_C',
        statement: '合成材料设定 A 先于 C。',
        content_type: 'supported',
        evidence_span_ids: [SPAN_A],
        source_claim_id: '20000000-0000-4000-8000-000000000001',
        source_claim_revision: 1,
      },
      {
        id: 'claim_B_C',
        statement: '合成材料设定 B 先于 C。',
        content_type: 'supported',
        evidence_span_ids: [SPAN_B],
        source_claim_id: '20000000-0000-4000-8000-000000000002',
        source_claim_revision: 1,
      },
      {
        id: 'claim_tool',
        statement: '合成材料设定工具 X 用于观察。',
        content_type: 'supported',
        evidence_span_ids: [SPAN_C],
        source_claim_id: '20000000-0000-4000-8000-000000000003',
        source_claim_revision: 1,
      },
    ],
    objectives: [
      { id: 'objective_tool', description: '辨认工具用途。', claim_ids: ['claim_tool'] },
      { id: 'objective_order', description: '理解 C 的两个前置步骤。', claim_ids: ['claim_A_C', 'claim_B_C'] },
    ],
    scenes: [
      {
        id: 'entry',
        title: '入口',
        text: '观察工坊里的工具。',
        content_type: 'supported',
        asset_ids: [],
        claim_ids: ['claim_tool'],
        tasks: [
          {
            id: 'hotspot_tool',
            type: 'hotspot',
            label: '观察工具 X',
            required: true,
            completion_flag: 'clue_seen',
            objective_ids: ['objective_tool'],
            claim_ids: ['claim_tool'],
            requires: { flag_equals: { id: 'never', value: false } },
            on_success: [],
            feedback: { success: '你看到工具 X。', failure: '还没找到工具。', claim_ids: ['claim_tool'] },
            hints: ['先看工作台左侧。'],
          },
        ],
        transitions: [
          {
            id: 'go_choice',
            label: '进入选择',
            requires: { flag_equals: { id: 'clue_seen', value: true } },
            target_scene: 'choice_scene',
          },
        ],
      },
      {
        id: 'choice_scene',
        title: '选择场景',
        text: '工具 X 的用途是什么？',
        content_type: 'supported',
        asset_ids: [],
        claim_ids: ['claim_tool'],
        tasks: [
          {
            id: 'choice_tool',
            type: 'choice',
            label: '选择用途',
            required: true,
            completion_flag: 'choice_done',
            objective_ids: ['objective_tool'],
            claim_ids: ['claim_tool'],
            requires: noRequires,
            on_success: [],
            feedback: { success: '正确。', failure: '再想想。', claim_ids: ['claim_tool'] },
            hints: ['回到入口再看一次。'],
            options: [
              { id: 'opt_right', label: '用于观察', correct: true, feedback: '正确。', on_success: [{ set_flag: 'bonus', value: true }] },
              { id: 'opt_wrong', label: '用于切割', correct: false, feedback: '工具 X 不用于切割。', on_success: [] },
            ],
          },
        ],
        transitions: [
          {
            id: 'go_sequence',
            label: '进入排序',
            requires: { flag_equals: { id: 'choice_done', value: true } },
            target_scene: 'sequence_scene',
          },
        ],
      },
      {
        id: 'sequence_scene',
        title: '排序场景',
        text: '按要求排列步骤。',
        content_type: 'supported',
        asset_ids: [],
        claim_ids: ['claim_A_C', 'claim_B_C'],
        tasks: [
          {
            id: 'sequence_steps',
            type: 'sequence',
            label: '排列 A、B、C',
            required: true,
            completion_flag: 'sequence_done',
            objective_ids: ['objective_order'],
            claim_ids: ['claim_A_C', 'claim_B_C'],
            requires: noRequires,
            on_success: [],
            feedback: { success: '顺序正确。', failure: 'C 必须排在最后。', claim_ids: ['claim_A_C', 'claim_B_C'] },
            hints: ['C 有两个前置步骤。'],
            items: [
              { id: 'A', label: 'A' },
              { id: 'B', label: 'B' },
              { id: 'C', label: 'C' },
            ],
            precedence: [
              { before: 'A', after: 'C', claim_id: 'claim_A_C' },
              { before: 'B', after: 'C', claim_id: 'claim_B_C' },
            ],
          },
        ],
        transitions: [
          {
            id: 'finish',
            label: '完成体验',
            requires: {
              all: [
                { flag_equals: { id: 'clue_seen', value: true } },
                { flag_equals: { id: 'choice_done', value: true } },
                { flag_equals: { id: 'sequence_done', value: true } },
              ],
            },
            target_scene: 'done',
          },
        ],
      },
      {
        id: 'done',
        title: '完成',
        text: '体验结束。',
        content_type: 'adaptation',
        asset_ids: [],
        claim_ids: [],
        tasks: [],
        transitions: [],
      },
    ],
    completion: { scene_id: 'done', required_flags: ['clue_seen', 'choice_done', 'sequence_done'] },
    asset_manifest: [],
  };
}
