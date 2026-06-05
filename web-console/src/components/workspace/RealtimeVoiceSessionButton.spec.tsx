import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { RealtimeVoiceSessionButton } from './RealtimeVoiceSessionButton';
import {
  openRealtimeVoiceSession,
} from '@/lib/meeting-voice/realtimeVoiceSessionClient';
import { createBrowserVadController } from '@/lib/meeting-voice/browserVadController';
import { fetchXttsHealth } from '@/lib/meeting-voice/voicePlaybackQueue';

const mocks = vi.hoisted(() => ({
  socket: {
    send: vi.fn(),
    close: vi.fn(),
    raw: {},
  },
  vad: {
    start: vi.fn(async () => undefined),
    pause: vi.fn(async () => undefined),
    destroy: vi.fn(async () => undefined),
  },
  sessionInput: null as any,
  vadInput: null as any,
}));

vi.mock('@/lib/meeting-voice/realtimeVoiceSessionClient', () => ({
  openRealtimeVoiceSession: vi.fn((input) => {
    mocks.sessionInput = input;
    return mocks.socket;
  }),
}));

vi.mock('@/lib/meeting-voice/browserVadController', () => ({
  createBrowserVadController: vi.fn(async (input) => {
    mocks.vadInput = input;
    return mocks.vad;
  }),
}));

vi.mock('@/lib/meeting-voice/voicePlaybackQueue', () => ({
  fetchXttsHealth: vi.fn(async () => ({ available: true })),
  VoicePlaybackQueue: class {
    interrupt = vi.fn();
    enqueue = vi.fn();
  },
}));

describe('RealtimeVoiceSessionButton', () => {
  afterEach(() => {
    vi.clearAllMocks();
    mocks.sessionInput = null;
    mocks.vadInput = null;
  });

  it('does not render without a meeting id', () => {
    render(
      <RealtimeVoiceSessionButton
        apiUrl="http://api.test"
        workspaceId="ws_test"
        meetingId={null}
      />,
    );

    expect(screen.queryByRole('button')).toBeNull();
  });

  it('renders without creating an interval polling loop', () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');

    render(
      <RealtimeVoiceSessionButton
        apiUrl="http://api.test"
        workspaceId="ws_test"
        meetingId="mtg_test"
      />,
    );

    expect(
      screen.getByRole('button', { name: 'Start realtime voice session' }),
    ).toBeTruthy();
    expect(setIntervalSpy).not.toHaveBeenCalled();
  });

  it('starts one websocket session and sends bounded VAD audio windows', async () => {
    render(
      <RealtimeVoiceSessionButton
        apiUrl="http://api.test"
        workspaceId="ws_test"
        meetingId="mtg_test"
      />,
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Start realtime voice session' }));
    });

    expect(fetchXttsHealth).toHaveBeenCalledWith('http://api.test');
    expect(openRealtimeVoiceSession).toHaveBeenCalledTimes(1);
    expect(mocks.sessionInput.workspaceId).toBe('ws_test');
    expect(mocks.sessionInput.meetingId).toBe('mtg_test');

    await act(async () => {
      await mocks.sessionInput.onOpen();
    });

    expect(mocks.socket.send).toHaveBeenCalledWith({ type: 'session_start' });
    expect(createBrowserVadController).toHaveBeenCalledTimes(1);
    expect(mocks.vad.start).toHaveBeenCalledTimes(1);

    await act(async () => {
      await mocks.vadInput.onSpeechEnd({
        audioBase64: 'UklGRg==',
        mimeType: 'audio/wav',
      });
    });

    expect(mocks.socket.send).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'audio_window',
        audio_base64: 'UklGRg==',
        mime_type: 'audio/wav',
      }),
    );
    const audioWindowCall = mocks.socket.send.mock.calls.find(
      ([message]) => message.type === 'audio_window',
    );
    const utteranceId = audioWindowCall?.[0].utterance_id;
    expect(mocks.socket.send).toHaveBeenCalledWith({
      type: 'utterance_end',
      utterance_id: utteranceId,
    });
  });
});
