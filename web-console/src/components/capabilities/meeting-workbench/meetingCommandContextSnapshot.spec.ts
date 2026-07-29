import { describe, expect, it } from 'vitest';

import { buildMeetingCommandContextSnapshot } from './meetingCommandContextSnapshot';

const selectedSummary = {
  ref: {
    uri: 'mindscape://ig/reference/ref_1',
    owner_pack: 'ig',
    object_kind: 'reference',
    object_id: 'ref_1',
    source_surface: 'ig_reference_workbench',
  },
  title: 'Reference 1',
  labels: [],
};

const packMention = {
  id: 'pack-create-scene',
  kind: 'pack' as const,
  label: 'Create scene',
  token: '@pack:create_scene',
  description: 'IG scene tool',
  ref: {
    id: 'create_scene',
    kind: 'pack' as const,
    token: '@pack:create_scene',
    label: 'Create scene',
    description: 'IG scene tool',
    capabilityCode: 'ig',
  },
};

const packTool = {
  id: 'create_scene',
  label: 'Create scene',
  description: 'Create one scene',
  capabilityCode: 'ig',
  requiredTools: [],
};

describe('buildMeetingCommandContextSnapshot', () => {
  it('builds one context authority for composer and voice transports', () => {
    const snapshot = buildMeetingCommandContextSnapshot({
      source: {
        kind: 'provided_text',
        text: 'Use @pack:create_scene for the selected reference',
      },
      composerCommand: '',
      activeMeetingId: 'mtg_1',
      mentionItems: [packMention],
      packTools: [packTool],
      selectedPackToolId: 'auto',
      effectiveSummary: selectedSummary,
      effectiveSelection: null,
      selectedNode: null,
      objectTitle: 'Reference 1',
      activeCapabilityCode: 'ig',
      graphSelection: null,
    });

    expect(snapshot).not.toBeNull();
    expect(snapshot?.selectedPackTool?.id).toBe('create_scene');
    expect(snapshot?.objectActionEntries).toEqual([
      { role: 'source', ref: selectedSummary.ref },
    ]);
    expect(snapshot?.voiceCommandContext.thread_id).toBe('mtg_1');
    expect(snapshot?.voiceCommandContext.context_objects)
      .toEqual(snapshot?.objectActionEntries);
    expect(snapshot?.voiceCommandContext.meeting_mentions)
      .toEqual(snapshot?.mentionRefs);
    expect(snapshot?.voiceCommandContext.requested_action).toMatchObject({
      verb: 'execute_playbook',
      pack_code: 'ig',
      playbook_code: 'create_scene',
      write_mode: 'recommendation_only',
    });
    expect(snapshot?.voiceCommandContext.metadata).toMatchObject({
      dispatch_mode: 'route_meeting_orchestration',
      action_parameters: {
        meeting_id: 'mtg_1',
        selected_object_uri: selectedSummary.ref.uri,
        force_meeting_orchestration: true,
      },
    });
  });

  it('returns null for an empty explicit text source', () => {
    expect(buildMeetingCommandContextSnapshot({
      source: { kind: 'provided_text', text: '   ' },
      composerCommand: 'must not be inferred',
      activeMeetingId: 'mtg_1',
      mentionItems: [],
      packTools: [],
      selectedPackToolId: 'auto',
      effectiveSummary: null,
      effectiveSelection: null,
      selectedNode: null,
      objectTitle: '',
      activeCapabilityCode: 'ig',
    })).toBeNull();
  });
});
