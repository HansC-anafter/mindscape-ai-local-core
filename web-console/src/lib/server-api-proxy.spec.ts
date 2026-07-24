import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  proxyToUpstream,
  resolveApiProxyUpstream,
  resolveBackendPathProxyUpstream,
} from './server-api-proxy';

const originalFetch = globalThis.fetch;
const originalEnv = { ...process.env };

beforeEach(() => {
  process.env = { ...originalEnv };
});

afterEach(() => {
  vi.restoreAllMocks();
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: originalFetch,
  });
  process.env = { ...originalEnv };
});

describe('server API proxy', () => {
  it('routes normal API paths to the backend with the original path and query', async () => {
    process.env.WEB_CONSOLE_EXECUTION_BACKEND_URL = 'http://backend:8200/';

    const resolution = resolveApiProxyUpstream('http://localhost:8300/api/v1/skills/?source=agent');

    expect(resolution).toEqual({
      baseUrl: 'http://backend:8200',
      pathname: '/api/v1/skills/',
      search: '?source=agent',
    });
  });

  it('routes install and administrative APIs to backend control only', () => {
    process.env.WEB_CONSOLE_BACKEND_URL = 'http://backend-control:8210/';
    process.env.WEB_CONSOLE_EXECUTION_BACKEND_URL = 'http://backend:8200/';

    expect(
      resolveApiProxyUpstream(
        'http://localhost:8300/api/v1/capability-packs/install-jobs/install-one',
      ),
    ).toEqual({
      baseUrl: 'http://backend-control:8210',
      pathname: '/api/v1/capability-packs/install-jobs/install-one',
      search: '',
    });
    expect(resolveApiProxyUpstream('http://localhost:8300/api/v1/admin/runtime')).toEqual({
      baseUrl: 'http://backend-control:8210',
      pathname: '/api/v1/admin/runtime',
      search: '',
    });
  });

  it('keeps device, meeting, and pack runtime APIs on execution', () => {
    process.env.WEB_CONSOLE_BACKEND_URL = 'http://backend-control:8210/';
    process.env.WEB_CONSOLE_EXECUTION_BACKEND_URL = 'http://backend:8200/';

    for (const pathname of [
      '/api/v1/workspaces/ws-1/device-bindings/sessions',
      '/api/v1/workspaces/ws-1/meetings',
      '/api/v1/capabilities/yogacoach/practice-diaries',
    ]) {
      expect(resolveApiProxyUpstream(`http://localhost:8300${pathname}`)).toEqual({
        baseUrl: 'http://backend:8200',
        pathname,
        search: '',
      });
    }
  });

  it('routes media API paths to the media proxy', async () => {
    process.env.MEDIA_PROXY_URL = 'http://media-proxy:8000/';

    const resolution = resolveApiProxyUpstream('http://localhost:8300/api/v1/media/files/a.png');

    expect(resolution).toEqual({
      baseUrl: 'http://media-proxy:8000',
      pathname: '/api/v1/media/files/a.png',
      search: '',
    });
  });

  it('routes host-runtime session gateway paths to the execution API', async () => {
    process.env.WEB_CONSOLE_BACKEND_URL = 'http://backend-control:8210/';
    process.env.WEB_CONSOLE_EXECUTION_BACKEND_URL = 'http://backend:8200/';

    expect(resolveApiProxyUpstream('http://localhost:8300/api/v1/host-runtime/status')).toEqual({
      baseUrl: 'http://backend:8200',
      pathname: '/api/v1/host-runtime/status',
      search: '',
    });
    expect(
      resolveApiProxyUpstream(
        'http://localhost:8300/api/v1/workspaces/ws-1/host-runtime/sessions/session-1/events?limit=20',
      ),
    ).toEqual({
      baseUrl: 'http://backend:8200',
      pathname: '/api/v1/workspaces/ws-1/host-runtime/sessions/session-1/events',
      search: '?limit=20',
    });
  });

  it('uses the shared service endpoint seed when env overrides are absent', () => {
    delete process.env.WEB_CONSOLE_BACKEND_URL;
    delete process.env.BACKEND_URL;
    delete process.env.NEXT_PUBLIC_BACKEND_URL;
    delete process.env.WEB_CONSOLE_EXECUTION_BACKEND_URL;
    delete process.env.WEB_CONSOLE_BACKEND_EXECUTION_URL;
    delete process.env.HOST_RUNTIME_BACKEND_URL;
    delete process.env.MEDIA_PROXY_URL;

    expect(resolveApiProxyUpstream('http://localhost:8300/api/v1/skills/')).toEqual({
      baseUrl: 'http://backend:8200',
      pathname: '/api/v1/skills/',
      search: '',
    });
    expect(resolveApiProxyUpstream('http://localhost:8300/api/v1/media/files/a.png')).toEqual({
      baseUrl: 'http://media-proxy:8000',
      pathname: '/api/v1/media/files/a.png',
      search: '',
    });
    expect(resolveApiProxyUpstream('http://localhost:8300/api/v1/host-runtime/status')).toEqual({
      baseUrl: 'http://backend:8200',
      pathname: '/api/v1/host-runtime/status',
      search: '',
    });
  });

  it('routes /health to backend readiness without using next rewrites', () => {
    process.env.BACKEND_URL = 'http://backend:8200/';

    const resolution = resolveBackendPathProxyUpstream('http://localhost:8300/health?full=1', '/health');

    expect(resolution).toEqual({
      baseUrl: 'http://backend:8200',
      pathname: '/health',
      search: '?full=1',
    });
  });

  it('retries idempotent GETs on transient upstream statuses', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response('busy', { status: 503 }))
      .mockResolvedValueOnce(Response.json({ ok: true }));
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: fetchMock,
    });

    const response = await proxyToUpstream(
      new Request('http://localhost:8300/api/v1/skills/', { method: 'GET' }),
      { baseUrl: 'http://backend:8200', pathname: '/api/v1/skills/', search: '' }
    );

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      'http://backend:8200/api/v1/skills/',
      expect.objectContaining({ cache: 'no-store', method: 'GET' })
    );
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ ok: true });
  });

  it('does not retry mutating methods', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('busy', { status: 503 }));
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: fetchMock,
    });

    const response = await proxyToUpstream(
      new Request('http://localhost:8300/api/v1/agent/run', {
        method: 'POST',
        body: JSON.stringify({ profile_id: 'default-user' }),
        headers: { 'Content-Type': 'application/json' },
      }),
      { baseUrl: 'http://backend:8200', pathname: '/api/v1/agent/run', search: '' }
    );

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(response.status).toBe(503);
  });

  it('returns a visible 502 when the backend cannot be reached after GET retries', async () => {
    const fetchMock = vi.fn().mockRejectedValue(
      Object.assign(new Error('connect refused'), {
        code: 'ECONNREFUSED',
      })
    );
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: fetchMock,
    });

    const response = await proxyToUpstream(
      new Request('http://localhost:8300/api/v1/skills/', { method: 'GET' }),
      { baseUrl: 'http://backend:8200', pathname: '/api/v1/skills/', search: '' }
    );

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(response.status).toBe(502);
    await expect(response.json()).resolves.toMatchObject({
      error: 'backend_proxy_unavailable',
      code: 'ECONNREFUSED',
    });
  });
});
