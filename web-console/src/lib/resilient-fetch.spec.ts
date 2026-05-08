import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  clearSharedGetInflightForTests,
  fetchWithIdempotentRetry,
  sharedGetFetch,
} from './resilient-fetch';

const originalFetch = globalThis.fetch;

afterEach(() => {
  vi.restoreAllMocks();
  clearSharedGetInflightForTests();
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: originalFetch,
  });
});

describe('sharedGetFetch', () => {
  it('deduplicates concurrent identical GETs while returning independent response clones', async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ ok: true }));
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: fetchMock,
    });

    const [first, second] = await Promise.all([
      sharedGetFetch('/api/v1/workspaces/ws-1/tasks?limit=20', { method: 'GET' }),
      sharedGetFetch('/api/v1/workspaces/ws-1/tasks?limit=20', { method: 'GET' }),
    ]);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    await expect(first.json()).resolves.toEqual({ ok: true });
    await expect(second.json()).resolves.toEqual({ ok: true });
  });

  it('retries transient GET statuses without retrying 500 application failures', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response('busy', { status: 503 }))
      .mockResolvedValueOnce(Response.json({ ok: true }))
      .mockResolvedValueOnce(new Response('bug', { status: 500 }));
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: fetchMock,
    });

    const recovered = await fetchWithIdempotentRetry('/api/v1/skills/', { method: 'GET' }, {
      retryBaseMs: 1,
    });
    const visibleFailure = await fetchWithIdempotentRetry('/api/v1/ig/insights/seeds', {
      method: 'GET',
    });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(recovered.status).toBe(200);
    expect(visibleFailure.status).toBe(500);
  });

  it('does not retry aborted requests', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new DOMException('aborted', 'AbortError'));
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: fetchMock,
    });

    await expect(
      fetchWithIdempotentRetry('/api/v1/workspaces/ws-1/health', { method: 'GET' }, {
        retryBaseMs: 1,
      })
    ).rejects.toMatchObject({ name: 'AbortError' });

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('does not retry mutating methods', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('busy', { status: 503 }));
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: fetchMock,
    });

    const response = await sharedGetFetch('/api/v1/agent/run', { method: 'POST' });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(response.status).toBe(503);
  });
});
