import { describe, expect, it } from 'vitest';

import {
  classifyProxyUpstream,
  computeNextDevRestartDelayMs,
  createFrontendProxyServer,
  isDevApiProxyPath,
  isFrontendLivenessPath,
  normalizeProxyLogPath,
  resolveNextDevArgs,
  resolveFrontendPrewarmPaths,
  resolveDevApiProxyTarget,
  shouldWriteProxyTimingLog,
} from './dev-proxy.mjs';

describe('frontend dev proxy', () => {
  it('keeps liveness paths on the proxy fast path only', () => {
    expect(isFrontendLivenessPath('/healthz')).toBe(true);
    expect(isFrontendLivenessPath('/healthz?probe=docker')).toBe(true);
    expect(isFrontendLivenessPath('/api/healthz')).toBe(true);
    expect(isFrontendLivenessPath('/api/v1/cloud-sync/status')).toBe(false);
    expect(isFrontendLivenessPath('/workspaces/ws-1/capabilities/ai_roles')).toBe(false);
  });

  it('sends same-origin API traffic to backend without involving Next dev', () => {
    expect(isDevApiProxyPath('/api/v1/cloud-sync/status')).toBe(true);
    expect(isDevApiProxyPath('/api/healthz')).toBe(false);
    expect(isDevApiProxyPath('/workspaces/ws-1/capabilities/ai_roles')).toBe(false);

    const target = resolveDevApiProxyTarget('/api/v1/cloud-sync/status?fresh=1');
    expect(target).toMatchObject({
      hostname: 'backend',
      port: 8200,
      path: '/api/v1/cloud-sync/status?fresh=1',
    });
  });

  it('keeps media API traffic on the media proxy upstream', () => {
    const target = resolveDevApiProxyTarget('/api/v1/media/assets/demo.png');
    expect(target).toMatchObject({
      hostname: 'media-proxy',
      port: 8000,
      path: '/api/v1/media/assets/demo.png',
    });
  });

  it('classifies upstreams and strips query strings from timing log paths', () => {
    expect(classifyProxyUpstream('/api/v1/cloud-sync/status?fresh=1')).toBe('backend_api');
    expect(classifyProxyUpstream('/api/v1/media/assets/demo.png?token=secret')).toBe('media_proxy');
    expect(classifyProxyUpstream('/workspaces/ws-1?tab=home')).toBe('next_dev');
    expect(normalizeProxyLogPath('/workspaces/ws-1?tab=home')).toBe('/workspaces/ws-1');
    expect(normalizeProxyLogPath('not a url?with=query')).toBe('/not%20a%20url');
  });

  it('reports failed liveness when the Next dev child is unavailable', async () => {
    const server = createFrontendProxyServer({ nextRunningRef: { current: false } });

    await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
    const address = server.address();
    const port = typeof address === 'object' && address ? address.port : null;

    try {
      const response = await fetch(`http://127.0.0.1:${port}/healthz`);
      const body = await response.json();

      expect(response.status).toBe(500);
      expect(body).toMatchObject({
        status: 'next_dev_unavailable',
        service: 'frontend',
        next_dev: 'exited',
      });
    } finally {
      await new Promise((resolve) => server.close(resolve));
    }
  });

  it('uses bounded backoff when restarting the Next dev child', () => {
    expect(computeNextDevRestartDelayMs(0)).toBe(1000);
    expect(computeNextDevRestartDelayMs(1)).toBe(2000);
    expect(computeNextDevRestartDelayMs(5)).toBe(30000);
    expect(computeNextDevRestartDelayMs(99)).toBe(30000);
  });

  it('resolves default and explicit frontend prewarm paths', () => {
    expect(resolveFrontendPrewarmPaths('', 'ws/one')).toEqual([]);
    expect(resolveFrontendPrewarmPaths('/a/{workspaceId}, /b', 'ws one')).toEqual([
      '/a/ws%20one',
      '/b',
    ]);
  });

  it('keeps Turbopack available as an explicit local Next dev opt-in', () => {
    expect(resolveNextDevArgs('127.0.0.1', 3010, true)).toEqual([
      'run',
      'dev',
      '--',
      '--turbo',
      '-H',
      '127.0.0.1',
      '-p',
      '3010',
    ]);
    expect(resolveNextDevArgs('127.0.0.1', 3010, false)).toEqual([
      'run',
      'dev',
      '--',
      '-H',
      '127.0.0.1',
      '-p',
      '3010',
    ]);
  });

  it('keeps default proxy timing logs to slow and error completions', () => {
    expect(shouldWriteProxyTimingLog({ event: 'start' }, 'slow', 1000)).toBe(false);
    expect(shouldWriteProxyTimingLog({ event: 'finish', status: 200, duration_ms: 200 }, 'slow', 1000)).toBe(false);
    expect(shouldWriteProxyTimingLog({ event: 'finish', status: 200, duration_ms: 1200 }, 'slow', 1000)).toBe(true);
    expect(shouldWriteProxyTimingLog({ event: 'finish', status: 500, duration_ms: 20 }, 'slow', 1000)).toBe(true);
    expect(shouldWriteProxyTimingLog({ event: 'upstream_error', duration_ms: 20 }, 'slow', 1000)).toBe(true);
    expect(shouldWriteProxyTimingLog({ event: 'finish', status: 200, duration_ms: 20 }, 'all', 1000)).toBe(true);
    expect(shouldWriteProxyTimingLog({ event: 'upstream_error', duration_ms: 20 }, 'none', 1000)).toBe(false);
  });
});
