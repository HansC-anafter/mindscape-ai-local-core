import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  buildVoiceSessionWebSocketUrl,
  openRealtimeVoiceSession,
} from './realtimeVoiceSessionClient';

describe('realtimeVoiceSessionClient', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('uses the existing meeting websocket route and carries command_context', () => {
    const sockets: FakeWebSocket[] = [];
    class FakeWebSocket {
      static OPEN = 1;
      readyState = 1;
      sent: string[] = [];
      onopen: (() => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onerror: (() => void) | null = null;
      onclose: (() => void) | null = null;
      constructor(readonly url: string) {
        sockets.push(this);
      }
      send(payload: string) {
        this.sent.push(payload);
      }
      close() {}
    }
    vi.stubGlobal('WebSocket', FakeWebSocket);

    expect(buildVoiceSessionWebSocketUrl({
      apiBase: 'https://api.test/',
      workspaceId: 'ws 1',
      meetingId: 'mtg/1',
      clientSessionId: 'session_1',
    })).toBe(
      'wss://api.test/api/v1/workspaces/ws%201/meetings/mtg%2F1/voice-sessions/session_1/stream',
    );

    const socket = openRealtimeVoiceSession({
      apiBase: 'https://api.test',
      workspaceId: 'ws_1',
      meetingId: 'mtg_1',
      clientSessionId: 'session_1',
    });
    socket.send({
      type: 'audio_window',
      utterance_id: 'utt_1',
      audio_base64: 'YXVkaW8=',
      mime_type: 'audio/wav',
      command_context: {
        context_objects: [],
        thread_id: 'mtg_1',
      },
    });

    expect(sockets).toHaveLength(1);
    expect(JSON.parse(sockets[0].sent[0]).command_context.thread_id).toBe('mtg_1');
  });
});
