import { afterEach, describe, expect, it, vi } from 'vitest';

import { submitVoiceTurn } from './voiceTurnClient';

describe('submitVoiceTurn', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends one normalized command_context without legacy context fields', async () => {
    const fetchMock = vi.fn(async (
      _input: RequestInfo | URL,
      _init?: RequestInit,
    ) => new Response(JSON.stringify({
      status: 'transcribed_command_submitted',
      transcript: 'Run it',
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    await submitVoiceTurn({
      apiBase: 'http://api.test/',
      workspaceId: 'ws 1',
      meetingId: 'mtg/1',
      clientTurnId: 'turn_1',
      audioBase64: 'YXVkaW8=',
      mimeType: 'audio/mp4',
      commandContext: {
        context_objects: [],
        thread_id: 'mtg/1',
        metadata: { graph_selection: { selection_hash: 'gsel_1' } },
      },
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(
      'http://api.test/api/v1/workspaces/ws%201/meetings/mtg%2F1/voice-turns',
    );
    const body = JSON.parse(String(init?.body));
    expect(body.command_context.thread_id).toBe('mtg/1');
    expect(body).not.toHaveProperty('context_objects');
    expect(body).not.toHaveProperty('metadata');
  });
});
