import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MeetingVoiceTurnButton } from './MeetingVoiceTurnButton';
import { submitVoiceTurn } from '@/lib/meeting-voice/voiceTurnClient';

describe('MeetingVoiceTurnButton', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('does not render without a meeting id', () => {
    render(
      <MeetingVoiceTurnButton
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
      <MeetingVoiceTurnButton
        apiUrl="http://api.test"
        workspaceId="ws_test"
        meetingId="mtg_test"
      />,
    );

    expect(screen.getByRole('button', { name: 'Start voice turn' })).toBeTruthy();
    expect(setIntervalSpy).not.toHaveBeenCalled();
  });
});

describe('submitVoiceTurn', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('posts a bounded voice turn payload to the workspace meeting route', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => ({
      ok: true,
      json: async () => ({
        status: 'ignored_empty_transcript',
        transcript: '',
        reason: 'empty_transcript',
      }),
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await submitVoiceTurn({
      apiBase: 'http://api.test/',
      workspaceId: 'ws_test',
      meetingId: 'mtg_test',
      clientTurnId: 'turn_test',
      audioBase64: 'UklGRg==',
      mimeType: 'audio/webm',
      language: 'auto',
    });

    expect(result.status).toBe('ignored_empty_transcript');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      'http://api.test/api/v1/workspaces/ws_test/meetings/mtg_test/voice-turns',
    );
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({
      client_turn_id: 'turn_test',
      audio_base64: 'UklGRg==',
      mime_type: 'audio/webm',
      language: 'auto',
      origin_surface: 'meeting_voice',
      context_objects: [],
      metadata: {},
    });
  });
});
