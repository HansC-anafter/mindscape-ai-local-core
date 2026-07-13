import assert from 'node:assert/strict';
import http from 'node:http';
import net from 'node:net';
import test from 'node:test';

import {
  createFrontendProxyServer,
} from './frontend-proxy-server.mjs';
import {
  normalizeCapabilitySupport,
} from './mobile-workbench-gateway/capability-support-contract.mjs';
import {
  createEffectivePolicyPayload,
  createGatewayConfig,
  createPolicyResolution,
  createSignedAccessJwt,
  createTestVerifier,
} from './mobile-workbench-gateway.test-support.mjs';

const CAPABILITY_CODE = 'live_interface_interpreter';
const API_PREFIX = `/api/v1/capabilities/${CAPABILITY_CODE}`;

function supportPayload(apiPrefixes) {
  return {
    capability_code: CAPABILITY_CODE,
    display_name: 'Live Interface Interpreter',
    supported: true,
    has_ui_components: true,
    host_route_template: `/workspaces/{workspaceId}/capability-ui-hosts/${CAPABILITY_CODE}`,
    main_page_component_codes: ['LiveInterfaceInterpreterWorkbench'],
    api_prefixes: apiPrefixes,
    request_scope_contract: 'no_remote_requests_v1',
  };
}

async function listen(server) {
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  return server.address().port;
}

async function close(server) {
  if (!server.listening) return;
  server.closeAllConnections?.();
  await new Promise((resolve) => server.close(resolve));
}

async function request(port, path, method) {
  return await new Promise((resolve, reject) => {
    const req = http.request({
      host: '127.0.0.1',
      port,
      path,
      method,
      headers: {
        host: 'remote-workbench.mindscapeai.app',
        'Cf-Access-Jwt-Assertion': createSignedAccessJwt(),
      },
    }, (res) => {
      res.resume();
      res.on('end', () => resolve(res));
    });
    req.on('error', reject);
    req.end();
  });
}

async function upgrade(port, path, method) {
  return await new Promise((resolve, reject) => {
    const socket = net.connect(port, '127.0.0.1', () => {
      socket.write(
        `${method} ${path} HTTP/1.1\r\n`
        + 'Host: remote-workbench.mindscapeai.app\r\n'
        + 'Connection: Upgrade\r\n'
        + 'Upgrade: websocket\r\n'
        + `Cf-Access-Jwt-Assertion: ${createSignedAccessJwt()}\r\n\r\n`,
      );
    });
    let output = '';
    socket.setEncoding('utf8');
    socket.on('data', (chunk) => { output += chunk; });
    socket.on('end', () => resolve(output));
    socket.on('error', reject);
  });
}

test('no-remote-request support rejects projected API prefixes', () => {
  assert.throws(
    () => normalizeCapabilitySupport(supportPayload([API_PREFIX]), CAPABILITY_CODE),
    /no_remote_requests_contract_exposes_api_prefix/,
  );
  const normalized = normalizeCapabilitySupport(supportPayload([]), CAPABILITY_CODE);
  assert.equal(normalized.supported, true);
  assert.deepEqual(normalized.apiPrefixes, []);
});

test('no-remote-request capability denies direct API HTTP and upgrade methods', async (t) => {
  let resolverCalls = 0;
  let deniedObservations = 0;
  let completedObservations = 0;
  const resolution = createPolicyResolution({
    capabilityCode: CAPABILITY_CODE,
    effectivePayload: createEffectivePolicyPayload({
      capabilityCodes: [CAPABILITY_CODE],
    }),
    apiPrefixes: [API_PREFIX],
    requestScopeContract: 'no_remote_requests_v1',
  });
  const server = createFrontendProxyServer({
    ingressMode: 'remote',
    getMobileWorkbenchGatewayConfig: () => createGatewayConfig(),
    verifyAccessToken: createTestVerifier(),
    policyResolver: async () => {
      resolverCalls += 1;
      return resolution;
    },
    remoteWorkbenchObservability: {
      createObservation: () => ({}),
      recordDeniedRequest: async () => {
        deniedObservations += 1;
      },
      recordCompletedRequest: async () => {
        completedObservations += 1;
      },
    },
  });
  const port = await listen(server);
  t.after(async () => close(server));
  const paths = [
    `${API_PREFIX}/health?workspace_id=workspace-a`,
    `${API_PREFIX}/sessions/session-a/interpret?workspace_id=workspace-a`,
  ];

  for (const path of paths) {
    for (const method of ['GET', 'POST']) {
      const response = await request(port, path, method);
      assert.equal(response.statusCode, 404, `${method} ${path}`);
      assert.equal(
        response.headers['x-mindscape-remote-auth-reason'],
        'capability_path_not_allowed',
      );
    }
  }
  for (const method of ['GET', 'POST']) {
    const output = await upgrade(port, paths[1], method);
    assert.match(output, /^HTTP\/1\.1 404 Not Found/m);
    assert.match(output, /X-Mindscape-Remote-Auth-Reason: capability_path_not_allowed/i);
  }
  assert.equal(resolverCalls, 6);
  assert.equal(deniedObservations, 4);
  assert.equal(completedObservations, 0);
});
