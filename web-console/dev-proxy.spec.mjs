import { describe, expect, it } from 'vitest';

import {
  computeNextDevRestartDelayMs,
  createFrontendProxyServer,
  isDevApiProxyPath,
  isFrontendLivenessPath,
  resolveDevApiProxyTarget,
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
});
