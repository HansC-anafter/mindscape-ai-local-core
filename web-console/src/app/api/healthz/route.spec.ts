import { afterEach, describe, expect, it, vi } from 'vitest';

import { GET } from './route';

const originalFetch = globalThis.fetch;

afterEach(() => {
  vi.restoreAllMocks();
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: originalFetch,
  });
});

describe('/api/healthz route', () => {
  it('returns local frontend liveness without probing backend', async () => {
    const fetchMock = vi.fn();
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: fetchMock,
    });

    const response = await GET();

    expect(response.status).toBe(200);
    expect(response.headers.get('cache-control')).toBe('no-store');
    await expect(response.json()).resolves.toEqual({
      status: 'ok',
      service: 'web-console',
      liveness: true,
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
