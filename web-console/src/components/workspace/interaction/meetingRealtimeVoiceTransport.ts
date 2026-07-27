import type { BrowserVadController } from '@/lib/meeting-voice/browserVadController';
import {
  openRealtimeVoiceSession,
  type RealtimeVoiceSessionEvent,
  type RealtimeVoiceSessionSocket,
} from '@/lib/meeting-voice/realtimeVoiceSessionClient';
import type { MeetingVoiceCommandContext } from '@/lib/meeting-voice/voiceTurnClient';
import type { FrozenWorkspaceInteractionTarget } from '@/lib/workspace-interaction/workspaceInteractionTarget';

export type MeetingRealtimeVoiceTransportState =
  | 'connecting'
  | 'listening'
  | 'transcribing'
  | 'interrupted'
  | 'closed'
  | 'speech_unavailable'
  | 'stale_target'
  | 'error';

export type MeetingRealtimeVoiceTransportHandle = {
  close: () => Promise<void>;
  interrupt: () => void;
};

function buildClientSessionId(): string {
  return `voice_session_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

function buildUtteranceId(): string {
  return `utt_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

function readRealtimeContext(snapshot: FrozenWorkspaceInteractionTarget): {
  meetingId: string;
  commandContext: MeetingVoiceCommandContext;
} {
  const meetingId = snapshot.context.meeting_id;
  const commandContext = snapshot.context.command_context;
  if (
    typeof meetingId !== 'string'
    || !commandContext
    || typeof commandContext !== 'object'
  ) {
    throw new Error('invalid_meeting_realtime_context');
  }
  return {
    meetingId,
    commandContext: commandContext as MeetingVoiceCommandContext,
  };
}

export async function startMeetingRealtimeVoiceTransport({
  apiUrl,
  workspaceId,
  snapshot,
  assertCurrent,
  onState,
  onTranscript,
  onCommandAccepted,
  onError,
}: {
  apiUrl: string;
  workspaceId: string;
  snapshot: FrozenWorkspaceInteractionTarget;
  assertCurrent: () => void;
  onState: (state: MeetingRealtimeVoiceTransportState) => void;
  onTranscript: (transcript: string) => void;
  onCommandAccepted: (input: {
    transcript: string;
    commandResponse: unknown;
  }) => void;
  onError: (error: Error) => void;
}): Promise<MeetingRealtimeVoiceTransportHandle> {
  const { meetingId, commandContext } = readRealtimeContext(snapshot);
  let socket: RealtimeVoiceSessionSocket | null = null;
  let vad: BrowserVadController | null = null;
  let closed = false;
  let lastTranscript = '';

  const destroy = async () => {
    if (closed) {
      return;
    }
    closed = true;
    await vad?.destroy().catch(() => undefined);
    socket?.close();
  };
  const close = async () => {
    socket?.send({ type: 'session_close' });
    await destroy();
  };
  const handleEvent = (event: RealtimeVoiceSessionEvent) => {
    if (event.transcript?.trim()) {
      lastTranscript = event.transcript.trim();
      onTranscript(lastTranscript);
    }
    if (event.type === 'session_ready' || event.type === 'transcript_final') {
      onState('listening');
    } else if (event.type === 'transcript_candidate') {
      onState('transcribing');
    } else if (event.type === 'command_submitted') {
      try {
        assertCurrent();
        onCommandAccepted({
          transcript: event.transcript?.trim() || lastTranscript || 'Voice command',
          commandResponse: event.command_response,
        });
      } catch (error) {
        onState('stale_target');
        onError(error instanceof Error ? error : new Error('stale_target'));
        void destroy();
        return;
      }
      onState('listening');
    } else if (event.type === 'speech_unavailable') {
      onState('speech_unavailable');
    } else if (event.type === 'interrupted') {
      onState('interrupted');
    } else if (event.type === 'cancelled') {
      onState('listening');
    } else if (event.type === 'session_closed') {
      onState('closed');
    } else if (event.type === 'session_error') {
      if (event.recoverable) {
        onState('listening');
      } else {
        onState('error');
      }
      onError(new Error(event.reason || event.message || 'voice_session_error'));
    }
  };

  onState('connecting');
  socket = openRealtimeVoiceSession({
    apiBase: apiUrl,
    workspaceId,
    meetingId,
    clientSessionId: buildClientSessionId(),
    onOpen: async () => {
      socket?.send({ type: 'session_start' });
      try {
        assertCurrent();
        const { createBrowserVadController } = await import(
          '@/lib/meeting-voice/browserVadController'
        );
        vad = await createBrowserVadController({
          onSpeechStart: () => onState('listening'),
          onSpeechEnd: async (window) => {
            try {
              assertCurrent();
            } catch (error) {
              onState('stale_target');
              onError(error instanceof Error ? error : new Error('stale_target'));
              await destroy();
              return;
            }
            const utteranceId = buildUtteranceId();
            onState('transcribing');
            socket?.send({
              type: 'audio_window',
              utterance_id: utteranceId,
              audio_base64: window.audioBase64,
              mime_type: window.mimeType,
              language: 'auto',
              command_context: commandContext,
            });
            socket?.send({ type: 'utterance_end', utterance_id: utteranceId });
          },
          onError: (error) => {
            onState('error');
            onError(error);
          },
        });
        await vad.start();
      } catch (error) {
        onState('error');
        onError(error instanceof Error ? error : new Error('vad_start_failed'));
        await destroy();
      }
    },
    onEvent: handleEvent,
    onError: (error) => {
      onState('error');
      onError(error);
    },
    onClose: () => {
      if (!closed) {
        onState('closed');
      }
    },
  });
  return {
    close,
    interrupt: () => {
      socket?.send({ type: 'interrupt' });
      onState('interrupted');
    },
  };
}
