import assert from 'node:assert/strict';
import http from 'node:http';
import test from 'node:test';

import { createFrontendProxyServer } from './frontend-proxy-server.mjs';
import {
  isInstalledCapabilityListProjectionRequest,
  writeInstalledCapabilityListProjection,
} from './mobile-workbench-gateway/installed-capability-projection.mjs';
import {
  createGatewayConfig,
  createPolicyResolution,
  createSignedAccessJwt,
  createTestVerifier,
  jsonResponse,
  requestLoopback,
} from './mobile-workbench-gateway.test-support.mjs';

async function listen(server) {
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  return server.address().port;
}

async function close(server) {
  if (!server?.listening) return;
  server.closeAllConnections?.();
  await new Promise((resolve) => server.close(resolve));
}

function captureResponse() {
  const captured = { statusCode: null, headers: null, body: '' };
  return {
    captured,
    res: {
      writeHead: (statusCode, headers) => {
        captured.statusCode = statusCode;
        captured.headers = headers;
      },
      end: (body = '') => { captured.body = String(body); },
    },
  };
}

function installedRow(code, supported = true) {
  return {
    id: code,
    code,
    display_name: code,
    mobile_workbench_gateway_support: {
      capability_code: code,
      supported,
      has_ui_components: supported,
      host_route_template: supported
        ? `/workspaces/{workspaceId}/capability-ui-hosts/${code}`
        : null,
      main_page_component_codes: supported ? ['TestWorkbenchPage'] : [],
      request_scope_contract: supported ? 'explicit_workspace_v1' : null,
      api_prefixes: [`/api/v1/capabilities/${code}`],
    },
  };
}

test('installed list projection emits only effective workspace capability codes', async () => {
  const { captured, res } = captureResponse();
  await writeInstalledCapabilityListProjection(res, {
    allowedCapabilityCodes: ['ig', 'yogacoach'],
    upstreamUrl: 'http://backend.test/api/v1/capability-packs/installed-capabilities',
    fetchImpl: async () => jsonResponse([
      { ...installedRow('ig'), display_name: 'IG' },
      { ...installedRow('browser_capture'), display_name: 'Browser' },
      { ...installedRow('yogacoach'), display_name: 'Yoga' },
      installedRow('unsupported_pack', false),
    ]),
  });

  assert.equal(captured.statusCode, 200);
  assert.deepEqual(JSON.parse(captured.body).map((row) => row.code), ['ig', 'yogacoach']);
  assert.doesNotMatch(captured.body, /browser_capture/);
  assert.doesNotMatch(captured.body, /unsupported_pack/);
  assert.equal(captured.headers['cache-control'], 'no-store');
});

test('projection is exact GET-only and malformed or duplicate upstream rows fail closed', async () => {
  assert.equal(isInstalledCapabilityListProjectionRequest(
    'GET',
    '/api/v1/capability-packs/installed-capabilities?workspace_id=workspace-a',
  ), true);
  assert.equal(isInstalledCapabilityListProjectionRequest(
    'POST',
    '/api/v1/capability-packs/installed-capabilities',
  ), false);
  for (const method of ['HEAD', 'OPTIONS']) {
    assert.equal(isInstalledCapabilityListProjectionRequest(
      method,
      '/api/v1/capability-packs/installed-capabilities',
    ), false);
  }
  const { res } = captureResponse();
  await assert.rejects(
    writeInstalledCapabilityListProjection(res, {
      allowedCapabilityCodes: ['ig'],
      upstreamUrl: 'http://backend.test/list',
      fetchImpl: async () => jsonResponse([installedRow('ig'), installedRow('ig')]),
    }),
    /installed_capabilities_payload_malformed/,
  );
  await assert.rejects(
    writeInstalledCapabilityListProjection(res, {
      allowedCapabilityCodes: ['ig'],
      upstreamUrl: 'http://backend.test/list',
      fetchImpl: async () => jsonResponse([{ code: 'ig' }]),
    }),
    /installed_capabilities_payload_malformed/,
  );
});

test('HEAD and OPTIONS cannot bypass projection or reach an upstream installed list', async (t) => {
  let upstreamCalls = 0;
  const upstream = http.createServer((_req, res) => {
    upstreamCalls += 1;
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end('[]');
  });
  const upstreamPort = await listen(upstream);
  const gateway = createFrontendProxyServer({
    ingressMode: 'remote',
    nextRunningRef: { current: true },
    getMobileWorkbenchGatewayConfig: () => createGatewayConfig(),
    verifyAccessToken: createTestVerifier(),
    policyResolver: async () => createPolicyResolution({ capabilityCode: null }),
    nextProxyTarget: { hostname: '127.0.0.1', port: upstreamPort },
  });
  const gatewayPort = await listen(gateway);
  t.after(async () => {
    await close(gateway);
    await close(upstream);
  });

  const token = createSignedAccessJwt();
  const url = `http://127.0.0.1:${gatewayPort}/api/v1/capability-packs/installed-capabilities?workspace_id=workspace-a`;
  for (const method of ['HEAD', 'OPTIONS']) {
    const response = await requestLoopback(url, {
      method,
      headers: {
        host: 'remote-workbench.mindscapeai.app',
        'Cf-Access-Jwt-Assertion': token,
      },
    });
    assert.equal(response.status, 404);
    assert.equal(response.headers.get('x-mindscape-remote-auth-reason'), 'capability_path_not_allowed');
  }
  assert.equal(upstreamCalls, 0);
});
