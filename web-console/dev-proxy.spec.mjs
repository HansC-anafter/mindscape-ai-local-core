import { afterEach, describe, expect, it } from 'vitest';

import {
  classifyProxyUpstream,
  clearDevApiReadCacheForTests,
  computeNextDevRestartDelayMs,
  createDeviceLinkIngressToken,
  copyProxyUpgradeHeaders,
  copyProxyResponseHeaders,
  createFrontendProxyServer,
  isDevApiProxyPath,
  isFrontendLivenessPath,
  isForegroundFrontendRequest,
  isCapabilityHostBootstrapRequest,
  isCapabilityHostRuntimeAssetRequest,
  normalizeProxyLogPath,
  resolveDevApiReadCacheTtlMs,
  resolveNextDevArgs,
  resolveFrontendPrewarmPaths,
  resolveDevApiProxyTarget,
  resolveApiRoutePlane,
  resolvePrewarmIdleDelayMs,
  shouldWriteProxyTimingLog,
} from './dev-proxy.mjs';
import { createBackendServer } from './dev-proxy.test-helpers.mjs';

describe('frontend dev proxy', () => {
  afterEach(() => {
    clearDevApiReadCacheForTests();
  });

  it('creates an unpredictable process-local device-link ingress token', () => {
    const first = createDeviceLinkIngressToken();
    const second = createDeviceLinkIngressToken();

    expect(first).toMatch(/^[a-f0-9]{64}$/);
    expect(second).toMatch(/^[a-f0-9]{64}$/);
    expect(second).not.toBe(first);
  });

  it('keeps liveness paths on the proxy fast path only', () => {
    expect(isFrontendLivenessPath('/healthz')).toBe(true);
    expect(isFrontendLivenessPath('/healthz?probe=docker')).toBe(true);
    expect(isFrontendLivenessPath('/api/healthz')).toBe(true);
    expect(isFrontendLivenessPath('/api/v1/cloud-sync/status')).toBe(false);
    expect(isFrontendLivenessPath('/workspaces/ws-1/capabilities/ai_roles')).toBe(false);
  });

  it('keeps frontend prewarm behind foreground activity', () => {
    expect(resolvePrewarmIdleDelayMs(1_000, 10_000, 45_000)).toBe(36_000);
    expect(resolvePrewarmIdleDelayMs(1_000, 60_000, 45_000)).toBe(0);
    expect(resolvePrewarmIdleDelayMs(0, 10_000, 45_000)).toBe(0);

    expect(isForegroundFrontendRequest('GET', '/workspaces/ws-1/capability-ui-hosts/ig')).toBe(true);
    expect(isForegroundFrontendRequest('GET', '/api/v1/ig/references/?workspace_id=ws-1')).toBe(true);
    expect(isForegroundFrontendRequest('GET', '/healthz')).toBe(false);
    expect(isForegroundFrontendRequest('HEAD', '/workspaces/ws-1/capability-ui-hosts/ig')).toBe(false);
    expect(isForegroundFrontendRequest('GET', '/_next/webpack-hmr')).toBe(false);
    expect(isForegroundFrontendRequest('GET', '/workspaces/ws-1/capability-ui-hosts/ig', {
      'x-mindscape-frontend-prewarm': '1',
    })).toBe(false);
  });

  it('sends default same-origin API traffic to execution without involving Next dev', () => {
    expect(isDevApiProxyPath('/api/v1/cloud-sync/status')).toBe(true);
    expect(isDevApiProxyPath('/api/healthz')).toBe(false);
    expect(isDevApiProxyPath('/workspaces/ws-1/capabilities/ai_roles')).toBe(false);

    const target = resolveDevApiProxyTarget('/api/v1/workspaces/ws-1/summary?fresh=1');
    expect(target).toMatchObject({
      hostname: 'backend',
      port: 8200,
      path: '/api/v1/workspaces/ws-1/summary?fresh=1',
      plane: 'execution',
    });
  });

  it('keeps control-only API operations on backend-control', () => {
    const target = resolveDevApiProxyTarget('/api/v1/capability-packs/install-from-file');
    expect(target).toMatchObject({
      hostname: 'backend-control',
      port: 8210,
      path: '/api/v1/capability-packs/install-from-file',
      plane: 'control',
    });
    expect(resolveApiRoutePlane('/api/v1/admin/capability-runtime/activate')).toMatchObject({
      plane: 'control',
    });
    expect(resolveDevApiProxyTarget('/api/v1/capability-packs/installed-capabilities/ig/ui-components')).toMatchObject({
      hostname: 'backend-control',
      port: 8210,
      path: '/api/v1/capability-packs/installed-capabilities/ig/ui-components',
      plane: 'control',
    });
    expect(resolveDevApiProxyTarget('/api/v1/workspaces/ws-1/device-bindings/PAIR1234/control')).toMatchObject({
      hostname: 'backend-control',
      port: 8210,
      path: '/api/v1/workspaces/ws-1/device-bindings/PAIR1234/control',
      plane: 'control',
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
    expect(classifyProxyUpstream('/api/v1/workspaces/ws-1/summary?fresh=1')).toBe('backend_execution_api');
    expect(classifyProxyUpstream('/api/v1/capability-packs/install-from-file')).toBe('backend_control_api');
    expect(classifyProxyUpstream('/api/v1/workspaces/ws-1/device-bindings/PAIR1234/control')).toBe('backend_control_api');
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

  it('serves capability host bootstrap without waiting for Next dev document compilation', async () => {
    expect(isCapabilityHostBootstrapRequest(
      'GET',
      '/workspaces/ws-1/capability-ui-hosts/ig?component=IGWorkbenchPage',
    )).toBe(true);
    expect(isCapabilityHostRuntimeAssetRequest(
      'GET',
      '/__mindscape-capability-host/react.production.min.js',
    )).toBe(true);

    const server = createFrontendProxyServer({ nextRunningRef: { current: false } });

    await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
    const address = server.address();
    const port = typeof address === 'object' && address ? address.port : null;

    try {
      const response = await fetch(`http://127.0.0.1:${port}/workspaces/ws-1/capability-ui-hosts/ig`);
      const body = await response.text();

      expect(response.status).toBe(200);
      expect(response.headers.get('content-type')).toContain('text/html');
      expect(body).toContain('<html lang="en" class="theme-warm">');
      expect(body).toContain('__mindscape-capability-host/app-layout.css');
      expect(body).toContain('__mindscape-capability-host/shell-runtime.browser.js');
      expect(body).toContain('mindscape-capability-host-config');
      expect(body).toContain('"workspaceId":"ws-1"');
      expect(body).toContain('"capabilityCode":"ig"');

      const runtimeResponse = await fetch(`http://127.0.0.1:${port}/__mindscape-capability-host/shell-runtime.browser.js`);
      const runtimeBody = await runtimeResponse.text();
      expect(runtimeResponse.status).toBe(200);
      expect(runtimeResponse.headers.get('content-type')).toContain('application/javascript');
      expect(runtimeBody).toContain('MindscapeRuntimeReact');
      expect(runtimeBody).toContain('__mindscapeCapabilityHostMetadataCache');
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

  it('keeps manifest-driven frontend capability prewarm opt-in', async () => {
    await expect(resolveFrontendPrewarmPaths('', 'ws/one', {
      installedCapabilities: [],
    })).resolves.toEqual([]);

    await expect(resolveFrontendPrewarmPaths('', 'ws/one', {
      installedCapabilities: [{
        code: 'ig',
        ui_prewarm: {
          enabled: true,
          surfaces: [{ path: '' }],
        },
      }, {
        code: 'performance_direction',
        ui_prewarm: {
          enabled: false,
          surfaces: [{ path: '' }],
        },
      }],
    })).resolves.toEqual([]);

    await expect(resolveFrontendPrewarmPaths('', 'ws/one', {
      capabilityPrewarmEnabled: true,
      installedCapabilities: [{
        code: 'ig',
        ui_prewarm: {
          enabled: true,
          surfaces: [{ path: '' }],
        },
      }, {
        code: 'performance_direction',
        ui_prewarm: {
          enabled: false,
          surfaces: [{ path: '' }],
        },
      }],
    })).resolves.toEqual([]);

    await expect(resolveFrontendPrewarmPaths('', 'ws/one', {
      capabilityPrewarmEnabled: true,
      capabilityHostPrewarmEnabled: true,
      installedCapabilities: [{
        code: 'ig',
        ui_prewarm: {
          enabled: true,
          surfaces: [{ path: '' }],
        },
      }, {
        code: 'performance_direction',
        ui_prewarm: {
          enabled: false,
          surfaces: [{ path: '' }],
        },
      }],
    })).resolves.toEqual([
      '/workspaces/ws%2Fone/capability-ui-hosts/ig',
    ]);

    await expect(resolveFrontendPrewarmPaths(
      '/a/{workspaceId}, /b, /capability-ui-hosts/ig/{workspaceId}, /workspaces/{workspaceId}/capabilities/performance_direction',
      'ws one',
      { installedCapabilities: [] },
    )).resolves.toEqual([
      '/a/ws%20one',
      '/b',
    ]);
  });

  it('keeps Turbopack available as an explicit local Next dev opt-in', () => {
    expect(resolveNextDevArgs('127.0.0.1', 3010, true)).toEqual([
      'exec',
      'next',
      'dev',
      '--turbo',
      '-H',
      '127.0.0.1',
      '-p',
      '3010',
    ]);
    expect(resolveNextDevArgs('127.0.0.1', 3010, false)).toEqual([
      'exec',
      'next',
      'dev',
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

  it('only enables short read-through caching for known expensive GET endpoints', () => {
    expect(resolveDevApiReadCacheTtlMs('/api/v1/ig/workbench/sidebar-summary', 'GET')).toBe(2000);
    expect(resolveDevApiReadCacheTtlMs('/api/v1/ig/browser-profiles', 'GET')).toBe(5000);
    expect(resolveDevApiReadCacheTtlMs('/api/v1/cloud-sync/status', 'GET')).toBe(2000);
    expect(resolveDevApiReadCacheTtlMs('/api/v1/workspaces/ws-1', 'GET')).toBe(0);
    expect(resolveDevApiReadCacheTtlMs('/api/v1/workspaces/ws-1/health', 'GET')).toBe(5000);
    expect(resolveDevApiReadCacheTtlMs('/api/v1/workspaces/ws-1/executions/ex-1/progress-snapshot', 'GET')).toBe(1000);
    expect(resolveDevApiReadCacheTtlMs('/api/v1/playbooks/execute/ex-1/status', 'GET')).toBe(1000);
    expect(resolveDevApiReadCacheTtlMs('/api/v1/ig/workbench/sidebar-summary', 'POST')).toBe(0);
    expect(resolveDevApiReadCacheTtlMs('/api/v1/ig/references/ref-1/pin', 'GET')).toBe(0);
  });

  it('does not preserve immutable cache headers for failed image responses', () => {
    expect(
      copyProxyResponseHeaders({}, '/api/v1/ig/references/ref-1/image?workspace_id=ws-1', 'GET', 500),
    ).toMatchObject({
      'cache-control': 'no-store',
    });
    expect(
      copyProxyResponseHeaders({}, '/api/v1/ig/references/ref-1/image?workspace_id=ws-1', 'GET', 200),
    ).toMatchObject({
      'cache-control': 'public, max-age=86400, immutable',
    });
  });

  it('preserves immutable cache headers for installed capability UI assets', () => {
    const assetPath = '/api/v1/capability-packs/installed-capabilities/ig/ui-assets/1.0.94/components/IGWorkbenchPage.mjs';
    expect(
      copyProxyResponseHeaders(
        { 'cache-control': 'public, max-age=31536000, immutable' },
        assetPath,
        'GET',
        200,
      ),
    ).toMatchObject({
      'cache-control': 'public, max-age=31536000, immutable',
    });
    expect(
      copyProxyResponseHeaders({}, assetPath, 'GET', 500),
    ).toMatchObject({
      'cache-control': 'no-store',
    });
  });

  it('restores WebSocket upgrade headers for the upstream Next dev handshake', () => {
    const headers = copyProxyUpgradeHeaders(
      {
        host: 'localhost:8300',
        connection: 'Upgrade',
        upgrade: 'websocket',
        'sec-websocket-key': 'dGhlIHNhbXBsZSBub25jZQ==',
        'sec-websocket-version': '13',
      },
      {
        hostname: '127.0.0.1',
        port: 3001,
      },
    );

    expect(headers).toMatchObject({
      host: '127.0.0.1:3001',
      connection: 'Upgrade',
      upgrade: 'websocket',
      'sec-websocket-key': 'dGhlIHNhbXBsZSBub25jZQ==',
      'sec-websocket-version': '13',
      'x-mindscape-web-console-proxy': '1',
    });
  });

  it('coalesces concurrent expensive GETs at the proxy without touching writes', async () => {
    const originalBackendUrl = process.env.WEB_CONSOLE_EXECUTION_BACKEND_URL;
    let requestCount = 0;
    const backend = await new Promise((resolve) => {
      const server = createBackendServer(() => {
        requestCount += 1;
        return new Promise((innerResolve) => {
          setTimeout(() => {
            innerResolve({
              status: 200,
              body: { ok: true, requestCount },
            });
          }, 30);
        });
      });
      server.listen(0, '127.0.0.1', () => resolve(server));
    });
    const proxy = createFrontendProxyServer({ nextRunningRef: { current: true } });

    await new Promise((resolve) => proxy.listen(0, '127.0.0.1', resolve));
    const backendAddress = backend.address();
    const proxyAddress = proxy.address();
    const backendPort = typeof backendAddress === 'object' && backendAddress ? backendAddress.port : null;
    const proxyPort = typeof proxyAddress === 'object' && proxyAddress ? proxyAddress.port : null;
    process.env.WEB_CONSOLE_EXECUTION_BACKEND_URL = `http://127.0.0.1:${backendPort}`;

    try {
      const [first, second] = await Promise.all([
        fetch(`http://127.0.0.1:${proxyPort}/api/v1/ig/workbench/sidebar-summary`),
        fetch(`http://127.0.0.1:${proxyPort}/api/v1/ig/workbench/sidebar-summary`),
      ]);

      await expect(first.json()).resolves.toEqual({ ok: true, requestCount: 1 });
      await expect(second.json()).resolves.toEqual({ ok: true, requestCount: 1 });
      expect(requestCount).toBe(1);
    } finally {
      if (originalBackendUrl === undefined) {
        delete process.env.WEB_CONSOLE_EXECUTION_BACKEND_URL;
      } else {
        process.env.WEB_CONSOLE_EXECUTION_BACKEND_URL = originalBackendUrl;
      }
      await new Promise((resolve) => proxy.close(resolve));
      await new Promise((resolve) => backend.close(resolve));
    }
  });
});
