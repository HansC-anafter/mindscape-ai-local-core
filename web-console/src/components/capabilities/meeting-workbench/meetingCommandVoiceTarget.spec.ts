import { beforeEach, describe, expect, it, vi } from 'vitest';

import { submitVoiceTurn } from '@/lib/meeting-voice/voiceTurnClient';

import type { MeetingCommandContextSnapshot } from './meetingCommandContextSnapshot';
import { createMeetingCommandVoiceTarget } from './meetingCommandVoiceTarget';

vi.mock('@/lib/meeting-voice/voiceTurnClient', () => ({
  submitVoiceTurn: vi.fn(),
}));
vi.mock('@/lib/meeting-voice/meetingClientActionEvent', () => ({
  dispatchMeetingClientAction: vi.fn(),
}));

const snapshot: MeetingCommandContextSnapshot = {
  command: 'Voice command',
  originSurface: 'meeting_workbench',
  mentionRefs: [],
  objectActionEntries: [],
  selectedPackTool: null,
  actionParameters: {
    meeting_id: 'mtg_1',
    graph_selection: { selection_hash: 'gsel_1' },
  },
  metadata: {
    active_capability_code: 'ig',
  },
  missingRequiredRoles: [],
  voiceCommandContext: {
    context_objects: [],
    thread_id: 'mtg_1',
    metadata: {
      action_parameters: {
        graph_selection: { selection_hash: 'gsel_1' },
      },
    },
  },
};

const t = ((key: string) => key) as any;

describe('createMeetingCommandVoiceTarget', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('submits once through the meeting route and returns acceptance to the shared seam', async () => {
    vi.mocked(submitVoiceTurn).mockResolvedValue({
      status: 'transcribed_command_submitted',
      transcript: 'Run selected graph',
      command_response: {
        command_id: 'cmd_1',
        dispatch_result: { meeting_orchestration: { task_ir_id: 'task_1' } },
      },
    });
    const onCommandAccepted = vi.fn();
    const target = createMeetingCommandVoiceTarget({
      apiUrl: 'http://api.test',
      workspaceId: 'ws_1',
      meetingId: 'mtg_1',
      snapshot,
      onCommandAccepted,
      t,
    });
    expect(target).not.toBeNull();

    const frozen = {
      workspaceId: 'ws_1',
      targetId: target!.targetId,
      targetKind: target!.targetKind,
      targetLabel: target!.targetLabel,
      targetRevision: target!.revision,
      submissionPolicy: target!.submissionPolicy,
      context: target!.freezeContext(),
      contextHash: 'fnv1a32:test',
    };
    const result = await target!.submitVoiceTurn({
      clientTurnId: 'turn_1',
      audioBase64: 'YXVkaW8=',
      mimeType: 'audio/mp4',
      language: 'auto',
    }, frozen);

    expect(submitVoiceTurn).toHaveBeenCalledTimes(1);
    expect(submitVoiceTurn).toHaveBeenCalledWith(expect.objectContaining({
      commandContext: snapshot.voiceCommandContext,
      mimeType: 'audio/mp4',
    }));
    expect(onCommandAccepted).toHaveBeenCalledTimes(1);
    expect(onCommandAccepted).toHaveBeenCalledWith({
      transcript: 'Run selected graph',
      commandResponse: expect.objectContaining({ command_id: 'cmd_1' }),
      snapshot,
    });
    expect(result.status).toBe('submitted');
  });

  it('does not settle a command when STT is unavailable', async () => {
    vi.mocked(submitVoiceTurn).mockResolvedValue({
      status: 'stt_unavailable',
      reason: 'stt_timeout',
    });
    const onCommandAccepted = vi.fn();
    const target = createMeetingCommandVoiceTarget({
      apiUrl: 'http://api.test',
      workspaceId: 'ws_1',
      meetingId: 'mtg_1',
      snapshot,
      onCommandAccepted,
      t,
    });

    await expect(target!.submitVoiceTurn({
      clientTurnId: 'turn_2',
      audioBase64: 'YXVkaW8=',
      mimeType: 'audio/webm',
      language: 'auto',
    }, {
      workspaceId: 'ws_1',
      targetId: target!.targetId,
      targetKind: target!.targetKind,
      targetLabel: target!.targetLabel,
      targetRevision: target!.revision,
      submissionPolicy: target!.submissionPolicy,
      context: target!.freezeContext(),
      contextHash: 'fnv1a32:test',
    })).rejects.toThrow('stt_timeout');
    expect(onCommandAccepted).not.toHaveBeenCalled();
  });
});
