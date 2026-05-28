import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';

import {
  getInstalledCapabilities,
  invalidateInstalledCapabilities,
} from './installed-capabilities-cache';

describe('installed capabilities cache', () => {
  const apiUrl = 'http://api.test';

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-05-28T00:00:00.000Z'));
    invalidateInstalledCapabilities(apiUrl);
  });

  afterEach(() => {
    invalidateInstalledCapabilities(apiUrl);
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('reuses the same in-flight request and cached result within the TTL', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ id: 'ig', code: 'ig' }],
    } as Response);
    vi.stubGlobal('fetch', fetchMock);

    const first = getInstalledCapabilities(apiUrl);
    const second = getInstalledCapabilities(apiUrl);

    expect(second).toBe(first);
    await expect(first).resolves.toEqual([{ id: 'ig', code: 'ig' }]);
    await expect(getInstalledCapabilities(apiUrl)).resolves.toEqual([{ id: 'ig', code: 'ig' }]);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(10 * 60 * 1000 + 1);
    await expect(getInstalledCapabilities(apiUrl)).resolves.toEqual([{ id: 'ig', code: 'ig' }]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('drops the cache entry after a failed request', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [{ id: 'review', code: 'review' }],
      } as Response);
    vi.stubGlobal('fetch', fetchMock);

    await expect(getInstalledCapabilities(apiUrl)).rejects.toThrow('offline');
    await expect(getInstalledCapabilities(apiUrl)).resolves.toEqual([{ id: 'review', code: 'review' }]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('invalidates a cached api base explicitly', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ id: 'ig', code: 'ig' }],
    } as Response);
    vi.stubGlobal('fetch', fetchMock);

    await getInstalledCapabilities(apiUrl);
    invalidateInstalledCapabilities(apiUrl);
    await getInstalledCapabilities(apiUrl);

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
