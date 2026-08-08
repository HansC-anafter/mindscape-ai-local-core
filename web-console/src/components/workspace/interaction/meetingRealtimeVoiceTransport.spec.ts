import { afterEach, describe, expect, it, vi } from 'vitest';

import type { FrozenWorkspaceInteractionTarget } from '@/lib/workspace-interaction/workspaceInteractionTarget';

import { startMeetingRealtimeVoiceTransport } from './meetingRealtimeVoiceTransport';

const realtimeMocks = vi.hoisted(() => ({
  open: vi.fn(),
  socketSend: vi.fn(),
  socketClose: vi.fn(),
  callbacks: null as Record<string, any> | null,
  vadStart: vi.fn(async () => undefined),
  vadDestroy: vi.fn(async () => undefined),
  vadOptions: null as Record<string, any> | null,
}));

vi.mock('@/lib/meeting-voice/realtimeVoiceSessionClient', () => ({
  openRealtimeVoiceSession: (input: Record<string, any>) => {
    realtimeMocks.open(input);
    realtimeMocks.callbacks = input;
    return {
      send: realtimeMocks.socketSend,
      close: realtimeMocks.socketClose,
      raw: {},
    };
  },
}));

vi.mock('@/lib/meeting-voice/browserVadController', () => ({
  createBrowserVadController: async (options: Record<string, any>) => {
    realtimeMocks.vadOptions = options;
    return {
      start: realtimeMocks.vadStart,
      pause: vi.fn(async () => undefined),
      destroy: realtimeMocks.vadDestroy,
    };
  },
}));

const snapshot: FrozenWorkspaceInteractionTarget = {
  workspaceId: 'ws_1',
  targetId: 'meeting:mtg_1',
  targetKind: 'meeting_command',
  targetLabel: 'Meeting',
  targetRevision: 'meeting:r1',
  submissionPolicy: 'direct_submit',
  contextHash: 'fnv1a32:12345678',
  context: {
    meeting_id: 'mtg_1',
    command_context: {
      context_objects: [],
      thread_id: 'mtg_1',
      metadata: {
        action_parameters: {
          graph_selection: { selection_hash: 'gsel_1' },
        },
      },
    },
  },
};

describe('startMeetingRealtimeVoiceTransport', () => {
  afterEach(() => {
    vi.clearAllMocks();
    realtimeMocks.callbacks = null;
    realtimeMocks.vadOptions = null;
  });

  it('loads VAD only after socket open and sends frozen context per utterance', async () => {
    const onCommandAccepted = vi.fn();
    const onSemanticResult = vi.fn();
    const onState = vi.fn();
    const handle = await startMeetingRealtimeVoiceTransport({
      apiUrl: 'http://api.test',
      workspaceId: 'ws_1',
      snapshot,
      assertCurrent: vi.fn(),
      onState,
      onTranscript: vi.fn(),
      onCommandAccepted,
      onSemanticResult,
      onError: vi.fn(),
    });

    expect(realtimeMocks.open).toHaveBeenCalledTimes(1);
    expect(realtimeMocks.vadStart).not.toHaveBeenCalled();
    await realtimeMocks.callbacks?.onOpen();
    expect(realtimeMocks.vadStart).toHaveBeenCalledTimes(1);

    await realtimeMocks.vadOptions?.onSpeechEnd({
      audioBase64: 'YXVkaW8=',
      mimeType: 'audio/wav',
    });
    const audioMessage = realtimeMocks.socketSend.mock.calls
      .map(([message]) => message)
      .find((message) => message.type === 'audio_window');
    expect(audioMessage.command_context.thread_id).toBe('mtg_1');
    expect(audioMessage.command_context.metadata.action_parameters.graph_selection)
      .toEqual({ selection_hash: 'gsel_1' });
    expect(realtimeMocks.socketSend.mock.calls.map(([message]) => message.type))
      .toContain('utterance_end');

    realtimeMocks.callbacks?.onEvent({
      type: 'command_submitted',
      transcript: 'Run it',
      command_response: { command_id: 'cmd_1' },
    });
    expect(onCommandAccepted).toHaveBeenCalledWith({
      transcript: 'Run it',
      commandResponse: { command_id: 'cmd_1' },
    });

    realtimeMocks.callbacks?.onEvent({
      type: 'semantic_clarification',
      transcript: 'How should I align?',
      semantic_result: {
        status: 'clarification_required',
        outcome: 'grounded_answer',
        decision_code: 'grounded_answer',
        transcript: 'How should I align?',
        answer_text: 'Keep the knee tracking over the second toe.',
        answer_language: 'en',
      },
    });
    expect(onSemanticResult).toHaveBeenCalledWith(expect.objectContaining({
      outcome: 'grounded_answer',
      answer_text: 'Keep the knee tracking over the second toe.',
    }));
    expect(onState).toHaveBeenCalledWith('answered');

    await handle.close();
    expect(realtimeMocks.vadDestroy).toHaveBeenCalledTimes(1);
    expect(realtimeMocks.socketClose).toHaveBeenCalledTimes(1);
  });
});
