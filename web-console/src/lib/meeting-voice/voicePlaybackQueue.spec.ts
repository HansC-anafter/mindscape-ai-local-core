import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  fetchXttsHealth,
  synthesizeXttsSpeech,
} from './voicePlaybackQueue';

describe('voicePlaybackQueue XTTS helpers', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('checks XTTS health through the existing host-services health route', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ status: 'healthy' }),
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchXttsHealth('http://api.test');

    expect(result.available).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      'http://api.test/api/v1/host/services/xtts/health',
    );
  });

  it('reports XTTS unavailable without throwing', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ status: 'unreachable', error: 'offline' }),
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchXttsHealth('http://api.test');

    expect(result).toEqual({ available: false, reason: 'offline' });
  });

  it('synthesizes speech through the existing XTTS route', async () => {
    const blob = new Blob(['RIFF'], { type: 'audio/wav' });
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({
      ok: true,
      blob: async () => blob,
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await synthesizeXttsSpeech({
      apiBase: 'http://api.test/',
      text: 'hello',
      language: 'en',
    });

    expect(result).toBe(blob);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://api.test/api/v1/host/services/xtts/tts');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({
      text: 'hello',
      language: 'en',
      output_format: 'wav',
    });
  });
});
