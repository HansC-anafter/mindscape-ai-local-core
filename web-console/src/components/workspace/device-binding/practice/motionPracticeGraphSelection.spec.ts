import { describe, expect, it } from 'vitest';

import { buildMotionPracticeLessonHandoffFromGraphSelection } from './motionPracticeGraphSelection';

describe('motionPracticeGraphSelection', () => {
  it('builds a bounded lesson handoff from a social video graph selection anchor', () => {
    const handoff = buildMotionPracticeLessonHandoffFromGraphSelection({
      capabilityCode: 'yogacoach',
      graphSelection: {
        owner_pack: 'social_video_refs',
        selection_kind: 'anchor',
        anchors: [
          {
            uri: 'mindscape://social_video_refs/instruction_ref/ref_hook_001',
            owner_pack: 'social_video_refs',
            object_kind: 'instruction_ref',
            object_id: 'ref_hook_001',
            workspace_id: 'ws_motion',
            selector: {
              instruction_ref_id: 'ref_hook_001',
              source_provider: 'youtube',
              canonical_url: 'https://www.youtube.com/watch?v=hook-flow',
              thumbnail: {
                url: 'https://i.ytimg.com/vi/hook-flow/hqdefault.jpg',
              },
              start_seconds: 5,
              end_seconds: 17,
            },
            source_surface: 'social_video_refs.refs',
            label: 'Hook Flow',
            role: 'source',
          },
        ],
        lens_code: 'instruction_memory',
        relation_scope: ['instruction_memory', 'metadata_only_reference'],
        node_limit: 8,
        relation_limit: 8,
        snapshot_budget: {
          max_nodes: 8,
          max_edges: 8,
          max_prompt_chars: 1200,
        },
        source_surface: 'social_video_refs.refs',
        governance_tags: ['reference_only', 'provider_neutral', 'no_media_download'],
        user_intent: 'launch_yogacoach_reference_lesson',
        selection_hash: 'gsel_test',
      },
    });

    expect(handoff).toMatchObject({
      capabilityCode: 'yogacoach',
      sourceKind: 'youtube_instruction_ref',
      sourceValue: 'https://www.youtube.com/watch?v=hook-flow',
      sourceTitle: 'Hook Flow',
      sourceProvider: 'youtube',
      thumbnailUrl: 'https://i.ytimg.com/vi/hook-flow/hqdefault.jpg',
    });
    expect(handoff?.courseChaptersInput).toContain('"chapter_id":"ref_hook_001"');
    expect(handoff?.courseChaptersInput).toContain('"thumbnail_url":"https://i.ytimg.com/vi/hook-flow/hqdefault.jpg"');
    expect(handoff?.courseChaptersInput).toContain('"start_ms":5000');
    expect(handoff?.courseChaptersInput).toContain('"end_ms":17000');
  });

  it('returns null for non social-video selections', () => {
    const handoff = buildMotionPracticeLessonHandoffFromGraphSelection({
      capabilityCode: 'yogacoach',
      graphSelection: {
        owner_pack: 'ig',
        selection_kind: 'anchor',
        anchors: [],
        lens_code: 'references',
        relation_scope: [],
        node_limit: 4,
        relation_limit: 4,
        snapshot_budget: {
          max_nodes: 4,
          max_edges: 4,
          max_prompt_chars: 800,
        },
        source_surface: 'ig.references',
        governance_tags: [],
      },
    } as never);

    expect(handoff).toBeNull();
  });
});
