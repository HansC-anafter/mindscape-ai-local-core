import { afterEach, describe, expect, it, vi } from 'vitest';

import { clearSharedGetInflightForTests } from './resilient-fetch';
import { clearSyncStatusCacheForTests, getPendingChanges, getSyncStatus } from './sync-api';

const originalFetch = globalThis.fetch;
const originalEnv = { ...process.env };

afterEach(() => {
  vi.restoreAllMocks();
  clearSharedGetInflightForTests();
  clearSyncStatusCacheForTests();
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: originalFetch,
  });
  process.env = { ...originalEnv };
});

describe('sync-api', () => {
  it('deduplicates concurrent sync status GET probes without dropping the poll', async () => {
    process.env.NEXT_PUBLIC_API_URL = 'http://backend.test/';
    const fetchMock = vi.fn().mockResolvedValue(
      Response.json({ configured: true, online: true, pending_changes: 0 })
    );
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: fetchMock,
    });

    const [first, second] = await Promise.all([
      getSyncStatus(),
      getSyncStatus(),
    ]);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      'http://backend.test/api/v1/cloud-sync/status',
      expect.objectContaining({ method: 'GET' })
    );
    expect(first).toEqual({ configured: true, online: true, pending_changes: 0 });
    expect(second).toEqual({ configured: true, online: true, pending_changes: 0 });
  });

  it('reuses the latest sync status for sequential chrome probes', async () => {
    process.env.NEXT_PUBLIC_API_URL = 'http://backend.test/';
    const fetchMock = vi.fn().mockResolvedValue(
      Response.json({ configured: false, online: false, pending_changes: 0 })
    );
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: fetchMock,
    });

    const first = await getSyncStatus();
    const second = await getSyncStatus();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(first).toEqual({ configured: false, online: false, pending_changes: 0 });
    expect(second).toEqual({ configured: false, online: false, pending_changes: 0 });
  });

  it('resolves the API base at call time instead of pinning a module-load value', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(Response.json({ configured: true, online: true, pending_changes: 1 }))
      .mockResolvedValueOnce(Response.json([]));
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: fetchMock,
    });

    process.env.NEXT_PUBLIC_API_URL = 'http://first-backend.test/';
    await getSyncStatus();

    process.env.NEXT_PUBLIC_API_URL = 'http://second-backend.test/';
    await getPendingChanges();

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      'http://first-backend.test/api/v1/cloud-sync/status',
      expect.objectContaining({ method: 'GET' })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      'http://second-backend.test/api/v1/cloud-sync/changes/pending',
      expect.objectContaining({ method: 'GET' })
    );
  });
});
