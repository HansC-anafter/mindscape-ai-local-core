import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import fs from 'node:fs';
import http from 'node:http';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  createFrontendProxyServer,
  createRemoteWorkbenchObservability,
  startRemoteWorkbenchListener,
} from '../dev-proxy.mjs';
import {
  createGatewayConfig,
  createPolicyResolution,
  createSignedAccessJwt,
  createTestVerifier,
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

test('remote listener starts only after one successful runtime config load', async () => {
  for (const ready of [false, true]) {
    let loadCalls = 0;
    let verifierCalls = 0;
    let createCalls = 0;
    let listenCalls = 0;
    const config = ready
      ? createGatewayConfig()
      : { ...createGatewayConfig(), remoteListenerReady: false };
    const fakeServer = new EventEmitter();
    fakeServer.listen = () => {
      listenCalls += 1;
      queueMicrotask(() => fakeServer.emit('listening'));
    };
    const configRef = { current: null };
    const result = await startRemoteWorkbenchListener({
      loadRuntimeConfig: async () => {
        loadCalls += 1;
        return config;
      },
      createVerifier: () => {
        verifierCalls += 1;
        return async () => ({ valid: false });
      },
      createServer: () => {
        createCalls += 1;
        return fakeServer;
      },
      configRef,
      host: '127.0.0.1',
      port: 3001,
    });
    assert.equal(loadCalls, 1);
    assert.equal(configRef.current, config);
    assert.equal(Boolean(result.server), ready);
    assert.equal(verifierCalls, ready ? 1 : 0);
    assert.equal(createCalls, ready ? 1 : 0);
    assert.equal(listenCalls, ready ? 1 : 0);
  }
});

test('local and remote listeners share implementation but not trust', async (t) => {
  const upstreamHeaders = [];
  const upstreamUpgradeHeaders = [];
  const upstream = http.createServer((req, res) => {
    upstreamHeaders.push(req.headers);
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ ok: true }));
  });
  upstream.on('upgrade', (req, socket) => {
    upstreamUpgradeHeaders.push(req.headers);
    socket.end('HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n');
  });
  const upstreamPort = await listen(upstream);
  const config = createGatewayConfig();
  let resolverCalls = 0;
  const resolver = async () => {
    resolverCalls += 1;
    return createPolicyResolution();
  };
  resolver.stats = () => ({
    effectivePolicyCacheEntries: resolverCalls,
    capabilitySupportCacheEntries: resolverCalls,
  });

  const localServer = createFrontendProxyServer({
    ingressMode: 'local',
    nextRunningRef: { current: true },
    getMobileWorkbenchGatewayConfig: () => config,
    policyResolver: resolver,
    nextProxyTarget: { hostname: '127.0.0.1', port: upstreamPort },
  });
  const remoteServer = createFrontendProxyServer({
    ingressMode: 'remote',
    nextRunningRef: { current: true },
    getMobileWorkbenchGatewayConfig: () => config,
    verifyAccessToken: createTestVerifier(),
    policyResolver: resolver,
    nextProxyTarget: { hostname: '127.0.0.1', port: upstreamPort },
  });
  const localPort = await listen(localServer);
  const remotePort = await listen(remoteServer);
  t.after(async () => {
    await close(localServer);
    await close(remoteServer);
    await close(upstream);
  });

  const localControl = await requestLoopback(
    `http://127.0.0.1:${localPort}/workspaces/workspace-a`,
  );
  assert.equal(localControl.status, 200);

  const validToken = createSignedAccessJwt();
  const remoteControl = await requestLoopback(
    `http://127.0.0.1:${remotePort}/api/v1/capabilities/mindscape_cloud_integration/mobile-workbench-gateway/runtime-policy/`,
    {
      headers: {
        host: 'remote-workbench.mindscapeai.app',
        'Cf-Access-Jwt-Assertion': validToken,
      },
    },
  );
  assert.equal(remoteControl.status, 404);
  assert.equal(remoteControl.headers.get('x-mindscape-remote-auth-stage'), 'principal_verified');

  const allowed = await requestLoopback(
    `http://127.0.0.1:${remotePort}/workspaces/workspace-a/capability-ui-hosts/yogacoach`,
    {
      headers: {
        host: 'remote-workbench.mindscapeai.app',
        'Cf-Access-Jwt-Assertion': validToken,
        'Cf-Access-Authenticated-User-Email': 'spoofed@example.com',
        'Cf-Access-Client-Id': 'spoofed-client',
        'Cf-Access-Client-Secret': 'spoofed-secret',
        authorization: 'Bearer client-value',
        cookie: 'theme=dark; CF_Authorization=edge-cookie',
        'x-user-id': 'spoofed-user',
        'x-mindscape-remote-ingress': 'client-spoof',
      },
    },
  );
  assert.equal(allowed.status, 200);
  assert.equal(resolverCalls, 1);
  const forwarded = upstreamHeaders.at(-1);
  assert.equal(forwarded['cf-access-jwt-assertion'], undefined);
  assert.equal(forwarded['cf-access-authenticated-user-email'], undefined);
  assert.equal(forwarded['cf-access-client-id'], undefined);
  assert.equal(forwarded['cf-access-client-secret'], undefined);
  assert.equal(forwarded.authorization, undefined);
  assert.equal(forwarded['x-user-id'], undefined);
  assert.equal(forwarded.cookie, 'theme=dark');
  assert.equal(forwarded['x-mindscape-web-console-proxy'], '1');
  assert.equal(forwarded['x-mindscape-remote-ingress'], 'remote_workbench');

  const upgradeOutput = await new Promise((resolve, reject) => {
    const socket = net.connect(remotePort, '127.0.0.1', () => {
      socket.write(
        'GET /workspaces/workspace-a/capability-ui-hosts/yogacoach HTTP/1.1\r\n'
        + 'Host: remote-workbench.mindscapeai.app\r\n'
        + 'Connection: Upgrade\r\n'
        + 'Upgrade: websocket\r\n'
        + `Cf-Access-Jwt-Assertion: ${validToken}\r\n`
        + 'Cf-Access-Authenticated-User-Email: spoofed@example.com\r\n'
        + 'Cf-Access-Client-Id: spoofed-client-a\r\n'
        + 'cf-access-client-id: spoofed-client-b\r\n'
        + 'Cf-Access-Client-Secret: spoofed-secret\r\n'
        + 'Cookie: CF_Authorization=edge-cookie\r\n\r\n',
      );
    });
    let output = '';
    socket.setEncoding('utf8');
    socket.on('data', (chunk) => { output += chunk; });
    socket.on('end', () => resolve(output));
    socket.on('error', reject);
  });
  assert.match(upgradeOutput, /^HTTP\/1\.1 101 Switching Protocols/m);
  const upgraded = upstreamUpgradeHeaders.at(-1);
  assert.equal(upgraded['cf-access-jwt-assertion'], undefined);
  assert.equal(upgraded['cf-access-authenticated-user-email'], undefined);
  assert.equal(upgraded['cf-access-client-id'], undefined);
  assert.equal(upgraded['cf-access-client-secret'], undefined);
  assert.equal(upgraded.cookie, undefined);

  const health = await requestLoopback(
    `http://127.0.0.1:${localPort}/api/v1/host/services/mobile-workbench-gateway/health`,
  );
  const healthPayload = await health.json();
  assert.equal(healthPayload.gateway.effective_policy_cache_entries, 2);
  assert.equal(healthPayload.gateway.capability_support_cache_entries, 2);
  assert.equal(healthPayload.gateway.upstream_effective_policy_calls, 0);
  assert.equal(healthPayload.gateway.upstream_capability_support_calls, 0);
});

test('external Access Referer is discarded for document HTTP but never for upgrade', async (t) => {
  let resolverCalls = 0;
  let upstreamRequests = 0;
  let upstreamUpgrades = 0;
  const upstream = http.createServer((_req, res) => {
    upstreamRequests += 1;
    res.writeHead(200, { 'content-type': 'text/html' });
    res.end('<main>YogaCoach</main>');
  });
  upstream.on('upgrade', (_req, socket) => {
    upstreamUpgrades += 1;
    socket.end('HTTP/1.1 101 Switching Protocols\r\n\r\n');
  });
  const upstreamPort = await listen(upstream);
  const server = createFrontendProxyServer({
    ingressMode: 'remote',
    getMobileWorkbenchGatewayConfig: () => createGatewayConfig(),
    verifyAccessToken: createTestVerifier(),
    policyResolver: async () => {
      resolverCalls += 1;
      return createPolicyResolution();
    },
    nextProxyTarget: { hostname: '127.0.0.1', port: upstreamPort },
  });
  const port = await listen(server);
  t.after(async () => {
    await close(server);
    await close(upstream);
  });
  const token = createSignedAccessJwt();
  const requestPath = '/workspaces/workspace-a/capability-ui-hosts/yogacoach';
  const externalReferer =
    'https://shy-resonance-542b.cloudflareaccess.com/cdn-cgi/access/login';
  const response = await requestLoopback(`http://127.0.0.1:${port}${requestPath}`, {
    headers: {
      host: 'remote-workbench.mindscapeai.app',
      'Cf-Access-Jwt-Assertion': token,
      referer: externalReferer,
      'sec-fetch-mode': 'navigate',
      'sec-fetch-dest': 'document',
      'sec-fetch-site': 'cross-site',
    },
  });
  assert.equal(response.status, 200);
  assert.equal(resolverCalls, 1);
  assert.equal(upstreamRequests, 1);

  const upgradeOutput = await new Promise((resolve, reject) => {
    const socket = net.connect(port, '127.0.0.1', () => {
      socket.write(
        `GET ${requestPath} HTTP/1.1\r\n`
        + 'Host: remote-workbench.mindscapeai.app\r\n'
        + 'Connection: Upgrade\r\n'
        + 'Upgrade: websocket\r\n'
        + 'Sec-Fetch-Mode: navigate\r\n'
        + 'Sec-Fetch-Dest: document\r\n'
        + `Referer: ${externalReferer}\r\n`
        + `Cf-Access-Jwt-Assertion: ${token}\r\n\r\n`,
      );
    });
    let output = '';
    socket.setEncoding('utf8');
    socket.on('data', (chunk) => { output += chunk; });
    socket.on('end', () => resolve(output));
    socket.on('error', reject);
  });
  assert.match(upgradeOutput, /^HTTP\/1\.1 403 Forbidden/m);
  assert.match(upgradeOutput, /X-Mindscape-Remote-Auth-Reason: request_context_mismatch/i);
  assert.equal(resolverCalls, 1);
  assert.equal(upstreamUpgrades, 0);
});

test('HTTP and upgrade use the same async membership denial', async (t) => {
  const config = createGatewayConfig();
  const outsiderToken = createSignedAccessJwt({
    claims: { sub: 'subject-outsider', email: 'outsider@example.com' },
  });
  const server = createFrontendProxyServer({
    ingressMode: 'remote',
    getMobileWorkbenchGatewayConfig: () => config,
    verifyAccessToken: createTestVerifier(),
    policyResolver: async () => createPolicyResolution(),
  });
  const port = await listen(server);
  t.after(async () => close(server));

  const response = await requestLoopback(
    `http://127.0.0.1:${port}/workspaces/workspace-a/capability-ui-hosts/yogacoach`,
    {
      headers: {
        host: 'remote-workbench.mindscapeai.app',
        'Cf-Access-Jwt-Assertion': outsiderToken,
      },
    },
  );
  assert.equal(response.status, 403);
  assert.equal(response.headers.get('x-mindscape-remote-auth-stage'), 'principal_verified');
  assert.equal(response.headers.get('x-mindscape-remote-auth-reason'), 'workspace_membership_required');

  const upgradeOutput = await new Promise((resolve, reject) => {
    const socket = net.connect(port, '127.0.0.1', () => {
      socket.write(
        'GET /workspaces/workspace-a/capability-ui-hosts/yogacoach HTTP/1.1\r\n'
        + 'Host: remote-workbench.mindscapeai.app\r\n'
        + 'Connection: Upgrade\r\n'
        + 'Upgrade: websocket\r\n'
        + `Cf-Access-Jwt-Assertion: ${outsiderToken}\r\n\r\n`,
      );
    });
    let output = '';
    socket.setEncoding('utf8');
    socket.on('data', (chunk) => { output += chunk; });
    socket.on('end', () => resolve(output));
    socket.on('error', reject);
  });
  assert.match(upgradeOutput, /^HTTP\/1\.1 403 Forbidden/m);
  assert.match(upgradeOutput, /X-Mindscape-Remote-Auth-Stage: principal_verified/i);
  assert.match(upgradeOutput, /X-Mindscape-Remote-Auth-Reason: workspace_membership_required/i);
});

test('POST boot assets are denied on both HTTP and upgrade paths', async (t) => {
  let resolverCalls = 0;
  const server = createFrontendProxyServer({
    ingressMode: 'remote',
    getMobileWorkbenchGatewayConfig: () => createGatewayConfig(),
    verifyAccessToken: createTestVerifier(),
    policyResolver: async () => {
      resolverCalls += 1;
      return createPolicyResolution();
    },
  });
  const port = await listen(server);
  t.after(async () => close(server));
  const token = createSignedAccessJwt();

  const response = await requestLoopback(`http://127.0.0.1:${port}/_next/static/chunk.js`, {
    method: 'POST',
    headers: {
      host: 'remote-workbench.mindscapeai.app',
      'Cf-Access-Jwt-Assertion': token,
    },
  });
  assert.equal(response.status, 403);
  assert.equal(response.headers.get('x-mindscape-remote-auth-stage'), 'principal_verified');
  assert.equal(response.headers.get('x-mindscape-remote-auth-reason'), 'route_workspace_required');

  const upgradeOutput = await new Promise((resolve, reject) => {
    const socket = net.connect(port, '127.0.0.1', () => {
      socket.write(
        'POST /_next/webpack-hmr HTTP/1.1\r\n'
        + 'Host: remote-workbench.mindscapeai.app\r\n'
        + 'Connection: Upgrade\r\n'
        + 'Upgrade: websocket\r\n'
        + `Cf-Access-Jwt-Assertion: ${token}\r\n\r\n`,
      );
    });
    let output = '';
    socket.setEncoding('utf8');
    socket.on('data', (chunk) => { output += chunk; });
    socket.on('end', () => resolve(output));
    socket.on('error', reject);
  });
  assert.match(upgradeOutput, /^HTTP\/1\.1 403 Forbidden/m);
  assert.match(upgradeOutput, /X-Mindscape-Remote-Auth-Stage: principal_verified/i);
  assert.match(upgradeOutput, /X-Mindscape-Remote-Auth-Reason: route_workspace_required/i);
  assert.equal(resolverCalls, 0);
});

test('dynamic Next handlers cannot wrap workspace data around the gateway', async (t) => {
  let upstreamRequests = 0;
  let resolverCalls = 0;
  const upstream = http.createServer((_req, res) => {
    upstreamRequests += 1;
    res.writeHead(200);
    res.end('protected-bytes');
  });
  const upstreamPort = await listen(upstream);
  const server = createFrontendProxyServer({
    ingressMode: 'remote',
    getMobileWorkbenchGatewayConfig: () => createGatewayConfig(),
    verifyAccessToken: createTestVerifier(),
    policyResolver: async () => {
      resolverCalls += 1;
      return createPolicyResolution();
    },
    nextProxyTarget: { hostname: '127.0.0.1', port: upstreamPort },
  });
  const port = await listen(server);
  t.after(async () => {
    await close(server);
    await close(upstream);
  });
  const outsiderToken = createSignedAccessJwt({
    claims: { sub: 'subject-outsider', email: 'outsider@example.com' },
  });
  const protectedTarget = encodeURIComponent(
    '/api/v1/workspaces/workspace-a/media-assets/asset-1/preview-content',
  );
  const cases = [
    [`/_next/image?url=${protectedTarget}&w=256&q=75`, 'route_workspace_required'],
    [`/_next/%69mage?url=${protectedTarget}&w=256&q=75`, 'route_workspace_required'],
    ['/_next/data/build/workspaces/workspace-a.json', 'route_workspace_required'],
    [
      `/_next/image?workspace_id=workspace-a&url=${protectedTarget}&w=256&q=75`,
      'workspace_membership_required',
    ],
  ];

  for (const [requestPath, reason] of cases) {
    const response = await requestLoopback(`http://127.0.0.1:${port}${requestPath}`, {
      headers: {
        host: 'remote-workbench.mindscapeai.app',
        'Cf-Access-Jwt-Assertion': outsiderToken,
      },
    });
    assert.equal(response.status, 403, requestPath);
    assert.equal(response.headers.get('x-mindscape-remote-auth-reason'), reason);
  }
  assert.equal(resolverCalls, 1);
  assert.equal(upstreamRequests, 0);
});

test('ambiguous repeated query scope is denied before resolver on HTTP and upgrade', async (t) => {
  let resolverCalls = 0;
  const server = createFrontendProxyServer({
    ingressMode: 'remote',
    getMobileWorkbenchGatewayConfig: () => createGatewayConfig(),
    verifyAccessToken: createTestVerifier(),
    policyResolver: async () => {
      resolverCalls += 1;
      return createPolicyResolution();
    },
  });
  const port = await listen(server);
  t.after(async () => close(server));
  const token = createSignedAccessJwt();

  const response = await requestLoopback(
    `http://127.0.0.1:${port}/workspaces/workspace-a/capability-ui-hosts/yogacoach`
    + '?workspace_id=workspace-a&workspace_id=workspace-b',
    {
      headers: {
        host: 'remote-workbench.mindscapeai.app',
        'Cf-Access-Jwt-Assertion': token,
      },
    },
  );
  assert.equal(response.status, 403);
  assert.equal(response.headers.get('x-mindscape-remote-auth-reason'), 'request_context_mismatch');

  const upgradeOutput = await new Promise((resolve, reject) => {
    const socket = net.connect(port, '127.0.0.1', () => {
      socket.write(
        'GET /workspaces/workspace-a/capability-ui-hosts/yogacoach'
        + '?capabilityCode=yogacoach&capabilityCode=ig HTTP/1.1\r\n'
        + 'Host: remote-workbench.mindscapeai.app\r\n'
        + 'Connection: Upgrade\r\n'
        + 'Upgrade: websocket\r\n'
        + `Cf-Access-Jwt-Assertion: ${token}\r\n\r\n`,
      );
    });
    let output = '';
    socket.setEncoding('utf8');
    socket.on('data', (chunk) => { output += chunk; });
    socket.on('end', () => resolve(output));
    socket.on('error', reject);
  });
  assert.match(upgradeOutput, /^HTTP\/1\.1 403 Forbidden/m);
  assert.match(upgradeOutput, /X-Mindscape-Remote-Auth-Reason: request_context_mismatch/i);
  assert.equal(resolverCalls, 0);
});

test('a blocked config never reports gateway health as ok', async (t) => {
  const blockedConfig = { ...createGatewayConfig(), remoteListenerReady: false };
  const server = createFrontendProxyServer({
    ingressMode: 'local',
    getMobileWorkbenchGatewayConfig: () => blockedConfig,
  });
  const port = await listen(server);
  t.after(async () => close(server));
  const response = await requestLoopback(
    `http://127.0.0.1:${port}/api/v1/host/services/mobile-workbench-gateway/health`,
  );
  const payload = await response.json();
  assert.notEqual(payload.status, 'ok');
  assert.equal(payload.gateway.remote_listener_ready, false);
});

test('subject candidate audit storage is bounded to owner-only permissions', async (t) => {
  const dataDir = await fs.promises.mkdtemp(path.join(os.tmpdir(), 'remote-workbench-audit-'));
  t.after(async () => fs.promises.rm(dataDir, { recursive: true, force: true }));
  const observability = createRemoteWorkbenchObservability({ dataDir });
  const observation = observability.createObservation({
    requestId: 1,
    requestUrl: '/workspaces/workspace-a',
    requestHeaders: { host: 'remote-workbench.mindscapeai.app' },
    requestResult: {
      context: { path: '/workspaces/workspace-a', workspaceId: 'workspace-a' },
      subject_candidate: {
        issuer: 'https://shy-resonance-542b.cloudflareaccess.com',
        subject: 'subject-global-a',
        email: 'hans@anafter.co',
      },
    },
    mobileWorkbenchGatewayConfig: {
      publicOrigin: 'https://remote-workbench.mindscapeai.app',
    },
  });
  await observability.recordDeniedRequest(observation, {
    requestResult: { reason_code: 'remote_access_enrollment_only' },
    statusCode: 403,
  });

  const activeLogPath = path.join(dataDir, 'access.current.ndjson');
  const directoryMode = (await fs.promises.stat(dataDir)).mode & 0o777;
  const fileMode = (await fs.promises.stat(activeLogPath)).mode & 0o777;
  assert.equal(directoryMode, 0o700);
  assert.equal(fileMode, 0o600);
  const raw = await fs.promises.readFile(activeLogPath, 'utf8');
  assert.match(raw, /"subject_candidate"/);
  assert.doesNotMatch(raw, /Cf-Access-Jwt-Assertion|eyJ/);
  const audit = await observability.readAuditTail({ originType: 'public_host' });
  assert.deepEqual(audit.events[0].subject_candidate, {
    issuer: 'https://shy-resonance-542b.cloudflareaccess.com',
    subject: 'subject-global-a',
    email: 'hans@anafter.co',
  });
});
