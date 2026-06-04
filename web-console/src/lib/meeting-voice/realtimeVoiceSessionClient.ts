import type { MicVAD } from '@ricky0123/vad-web';

export type RealtimeVoiceSessionState =
  | 'idle'
  | 'listening'
  | 'transcribing'
  | 'speaking'
  | 'interrupted'
  | 'closed';

export type RealtimeVoiceSessionEventType =
  | 'session_ready'
  | 'transcript_candidate'
  | 'transcript_final'
  | 'command_submitted'
  | 'speech_unavailable'
  | 'interrupted'
  | 'cancelled'
  | 'session_closed'
  | 'session_error';

export type RealtimeVoiceSessionEvent = {
  type: RealtimeVoiceSessionEventType;
  workspace_id: string;
  meeting_id: string;
  client_session_id: string;
  state?: RealtimeVoiceSessionState;
  utterance_id?: string;
  transcript?: string;
  language?: string | null;
  duration?: number | null;
  audio_byte_count?: number | null;
  command_response?: unknown;
  reason?: string;
  message?: string;
  recoverable?: boolean;
};

export type RealtimeVoiceClientMessage =
  | { type: 'session_start' }
  | {
      type: 'audio_window';
      utterance_id: string;
      audio_base64: string;
      mime_type: string;
      language?: string;
      context_objects?: unknown[];
      metadata?: Record<string, unknown>;
    }
  | { type: 'utterance_end'; utterance_id: string }
  | { type: 'interrupt' }
  | { type: 'cancel' }
  | { type: 'ack' }
  | { type: 'session_close' };

export type RealtimeVoiceSessionSocket = {
  send: (message: RealtimeVoiceClientMessage) => void;
  close: () => void;
  raw: WebSocket;
};

export type OpenRealtimeVoiceSessionInput = {
  apiBase: string;
  workspaceId: string;
  meetingId: string;
  clientSessionId: string;
  onOpen?: () => void;
  onEvent?: (event: RealtimeVoiceSessionEvent) => void;
  onError?: (error: Error) => void;
  onClose?: () => void;
};

export type VadSpeechWindow = {
  audioBase64: string;
  mimeType: 'audio/wav';
};

export type BrowserVadController = {
  start: () => Promise<void>;
  pause: () => Promise<void>;
  destroy: () => Promise<void>;
};

export type CreateBrowserVadInput = {
  onSpeechStart?: () => void;
  onSpeechEnd: (window: VadSpeechWindow) => Promise<void> | void;
  onError?: (error: Error) => void;
};

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

function getBrowserOrigin(): string {
  if (typeof window === 'undefined') {
    return 'http://localhost:8300';
  }
  return window.location.origin;
}

export function buildVoiceSessionWebSocketUrl({
  apiBase,
  workspaceId,
  meetingId,
  clientSessionId,
}: {
  apiBase: string;
  workspaceId: string;
  meetingId: string;
  clientSessionId: string;
}): string {
  const base = trimTrailingSlash(apiBase || getBrowserOrigin()) || getBrowserOrigin();
  const url = new URL(base, getBrowserOrigin());
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.pathname = `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/meetings/${encodeURIComponent(meetingId)}/voice-sessions/${encodeURIComponent(clientSessionId)}/stream`;
  url.search = '';
  return url.toString();
}

export function openRealtimeVoiceSession(
  input: OpenRealtimeVoiceSessionInput,
): RealtimeVoiceSessionSocket {
  const socket = new WebSocket(buildVoiceSessionWebSocketUrl(input));
  socket.onopen = () => input.onOpen?.();
  socket.onmessage = (message) => {
    try {
      input.onEvent?.(JSON.parse(String(message.data)) as RealtimeVoiceSessionEvent);
    } catch (error) {
      input.onError?.(
        error instanceof Error ? error : new Error('invalid_voice_session_event'),
      );
    }
  };
  socket.onerror = () => input.onError?.(new Error('voice_session_socket_error'));
  socket.onclose = () => input.onClose?.();
  return {
    raw: socket,
    send: (message) => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(message));
      }
    },
    close: () => socket.close(),
  };
}

export async function createBrowserVadController(
  input: CreateBrowserVadInput,
): Promise<BrowserVadController> {
  const vad = await import('@ricky0123/vad-web');
  const micVad: MicVAD = await vad.MicVAD.new({
    model: 'legacy',
    startOnLoad: false,
    baseAssetPath: '/vad/',
    onnxWASMBasePath: '/vad/',
    onFrameProcessed: () => undefined,
    onVADMisfire: () => undefined,
    onSpeechRealStart: () => undefined,
    onSpeechStart: () => input.onSpeechStart?.(),
    onSpeechEnd: async (audio: Float32Array) => {
      try {
        const wavBuffer = vad.utils.encodeWAV(audio, 1, 16000, 1, 16);
        await input.onSpeechEnd({
          audioBase64: vad.utils.arrayBufferToBase64(wavBuffer),
          mimeType: 'audio/wav',
        });
      } catch (error) {
        input.onError?.(
          error instanceof Error ? error : new Error('vad_audio_window_failed'),
        );
      }
    },
  });
  return {
    start: () => micVad.start(),
    pause: () => micVad.pause(),
    destroy: () => micVad.destroy(),
  };
}
