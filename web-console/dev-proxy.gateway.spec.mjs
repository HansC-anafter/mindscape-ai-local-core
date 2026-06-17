import http from 'node:http';
import { afterEach, describe, expect, it } from 'vitest';

import {
  createFrontendProxyServer,
  createRemoteWorkbenchObservability,
  isDeviceLinkHttpsHealthRequest,
  resolveMobileWorkbenchGatewayConfig,
} from './dev-proxy.mjs';
import { cleanupTempDirs, makeTempDir } from './dev-proxy.test-helpers.mjs';

describe('frontend dev proxy gateway surfaces', () => {
  afterEach(() => {
    cleanupTempDirs();
  });

  it('exposes mobile workbench gateway health through the proxy surface', async () => {
    const server = createFrontendProxyServer({
      nextRunningRef: { current: true },
      mobileWorkbenchGatewayConfig: resolveMobileWorkbenchGatewayConfig({
        MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
        MOBILE_WORKBENCH_GATEWAY_ALLOWLIST_EMAILS: 'admin@mindscape.ai',
        MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN: 'https://remote-workbench.mindscapeai.app',
        MOBILE_WORKBENCH_GATEWAY_JWT_AUDIENCE: 'remote-workbench',
      }),
    });

    await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
    const address = server.address();
    const port = typeof address === 'object' && address ? address.port : null;

    try {
      const response = await fetch(`http://127.0.0.1:${port}/api/v1/host/services/mobile-workbench-gateway/health`);
      const body = await response.json();

      expect(response.status).toBe(200);
      expect(body).toMatchObject({
        status: 'ok',
        service: 'mobile-workbench-gateway',
        enabled: true,
        reason: 'enabled',
        gateway: expect.objectContaining({
          jwt_audience: ['remote-workbench'],
          allowlist_emails: ['admin@mindscape.ai'],
          public_origin: 'https://remote-workbench.mindscapeai.app',
        }),
      });
    } finally {
      await new Promise((resolve) => server.close(resolve));
    }
  });

  it('exposes remote workbench summary and audit only to the loopback control plane', async () => {
    const remoteWorkbenchObservability = createRemoteWorkbenchObservability({
      dataDir: makeTempDir(),
      loadRunnerSnapshot: async () => ({
        status: 'ok',
        runners: [{
          runner_id: 'browser-1',
          runner_type: 'browser_local',
          inflight: 1,
          max_inflight: 3,
          admission: {
            state: 'healthy',
            reasons: [],
          },
        }],
      }),
    });
    const gatewayConfig = resolveMobileWorkbenchGatewayConfig({
      MOBILE_WORKBENCH_GATEWAY_ENABLED: '1',
      MOBILE_WORKBENCH_GATEWAY_PUBLIC_ORIGIN: 'https://remote-workbench.mindscapeai.app',
    });

    const proxyObservation = remoteWorkbenchObservability.createObservation({
      requestId: 1,
      requestUrl: '/workspaces/ws-1/capability-ui-hosts/yogacoach',
      requestMethod: 'GET',
      requestHeaders: {
        host: 'remote-workbench.mindscapeai.app',
      },
      requestResult: {
        context: {
          path: '/workspaces/ws-1/capability-ui-hosts/yogacoach',
          workspaceId: 'ws-1',
          capabilityCode: 'yogacoach',
        },
      },
      mobileWorkbenchGatewayConfig: gatewayConfig,
    });
    await remoteWorkbenchObservability.recordCompletedRequest(proxyObservation, {
      event: 'finish',
      statusCode: 200,
      responseBytes: 2048,
      durationMs: 140,
      upstreamKind: 'next_dev',
      upstreamStatus: 200,
      upstreamHeaderMs: 30,
    });

    const server = createFrontendProxyServer({
      nextRunningRef: { current: true },
      mobileWorkbenchGatewayConfig: gatewayConfig,
      remoteWorkbenchObservability,
    });

    await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
    const address = server.address();
    const port = typeof address === 'object' && address ? address.port : null;

    try {
      const summaryResponse = await fetch(
        `http://127.0.0.1:${port}/api/v1/host/services/mobile-workbench-gateway/summary?workspace_id=ws-1&capability_code=yogacoach`,
      );
      const summaryBody = await summaryResponse.json();

      expect(summaryResponse.status).toBe(200);
      expect(summaryBody.request_totals).toMatchObject({
        total: 1,
        proxied: 1,
        denied: 0,
      });

      const auditResponse = await fetch(
        `http://127.0.0.1:${port}/api/v1/host/services/mobile-workbench-gateway/audit?workspace_id=ws-1&capability_code=yogacoach&limit=5`,
      );
      const auditBody = await auditResponse.json();

      expect(auditResponse.status).toBe(200);
      expect(auditBody.events).toHaveLength(1);
      expect(auditBody.events[0]).toMatchObject({
        workspace_id: 'ws-1',
        capability_code: 'yogacoach',
        origin_type: 'public_host',
      });

      const remoteDenied = await new Promise((resolve, reject) => {
        const request = http.request(
          {
            hostname: '127.0.0.1',
            port,
            method: 'GET',
            path: '/api/v1/host/services/mobile-workbench-gateway/summary?workspace_id=ws-1',
            headers: {
              host: 'remote-workbench.mindscapeai.app',
            },
          },
          (response) => {
            let body = '';
            response.setEncoding('utf8');
            response.on('data', (chunk) => {
              body += chunk;
            });
            response.on('end', () => {
              resolve({
                statusCode: response.statusCode,
                body,
              });
            });
          },
        );
        request.on('error', reject);
        request.end();
      });

      expect(remoteDenied).toMatchObject({
        statusCode: 404,
      });
    } finally {
      await new Promise((resolve) => server.close(resolve));
    }
  });

  it('exposes device-link HTTPS public origin through the local control-plane proxy surface', async () => {
    const server = createFrontendProxyServer({
      nextRunningRef: { current: true },
    });

    expect(isDeviceLinkHttpsHealthRequest('/api/v1/host/services/device-link-https/health')).toBe(true);
    expect(isDeviceLinkHttpsHealthRequest('/api/v1/host/services/device-link-https/health', 'POST')).toBe(false);

    await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
    const address = server.address();
    const port = typeof address === 'object' && address ? address.port : null;

    try {
      const response = await fetch(`http://127.0.0.1:${port}/api/v1/host/services/device-link-https/health`);
      const body = await response.json();

      expect(response.status).toBe(200);
      expect(body).toMatchObject({
        service: 'device-link-https',
        enabled: expect.any(Boolean),
        reason: expect.any(String),
      });
      expect(body).toHaveProperty('public_origin');
    } finally {
      await new Promise((resolve) => server.close(resolve));
    }
  });
});
