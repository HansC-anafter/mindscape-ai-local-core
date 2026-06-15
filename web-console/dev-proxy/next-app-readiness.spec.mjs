import { describe, expect, it, vi } from 'vitest';

import {
  DEFAULT_NEXT_APP_READINESS_PATHS,
  parseNextAppReadinessPaths,
  probeNextAppReadiness,
  probeNextAppRoute,
  resolveNextAppReadinessConfig,
} from './next-app-readiness.mjs';

describe('next app readiness probe', () => {
  it('parses explicit paths and falls back to bounded defaults', () => {
    expect(parseNextAppReadinessPaths('/healthz, workspaces/ws/capability-ui-hosts/ig, /healthz')).toEqual([
      '/healthz',
      '/workspaces/ws/capability-ui-hosts/ig',
    ]);
    expect(parseNextAppReadinessPaths('')).toEqual(DEFAULT_NEXT_APP_READINESS_PATHS);
  });

  it('resolves a direct Next dev probe config from env', () => {
    expect(resolveNextAppReadinessConfig({
      NEXT_DEV_HOST: '127.0.0.2',
      NEXT_DEV_PORT: '3901',
      FRONTEND_APP_READINESS_TIMEOUT_MS: '9000',
      FRONTEND_APP_READINESS_PATHS: '/healthz,/workspaces/ws',
    })).toEqual({
      host: '127.0.0.2',
      port: 3901,
      timeoutMs: 9000,
      paths: ['/healthz', '/workspaces/ws'],
    });
  });

  it('reports a bounded route probe result without treating 404 as transport failure', async () => {
    const fetchImpl = vi.fn(async () => ({
      status: 404,
      arrayBuffer: async () => new Uint8Array([1, 2]).buffer,
    }));

    const result = await probeNextAppRoute(
      {
        host: '127.0.0.1',
        port: 3001,
        timeoutMs: 12000,
        paths: ['/favicon.ico'],
      },
      '/favicon.ico',
      { fetchImpl },
    );

    expect(fetchImpl).toHaveBeenCalledWith('http://127.0.0.1:3001/favicon.ico', expect.any(Object));
    expect(result).toMatchObject({
      path: '/favicon.ico',
      status: 404,
      ok: true,
      bytes: 2,
    });
  });

  it('marks failed probes as not ready', async () => {
    const fetchImpl = vi.fn(async () => {
      throw new Error('connection refused');
    });

    const result = await probeNextAppReadiness(
      {
        host: '127.0.0.1',
        port: 3001,
        timeoutMs: 1,
        paths: ['/healthz'],
      },
      { fetchImpl },
    );

    expect(result.ok).toBe(false);
    expect(result.results[0]).toMatchObject({
      path: '/healthz',
      status: null,
      ok: false,
      error: 'Error',
      message: 'connection refused',
    });
  });
});
