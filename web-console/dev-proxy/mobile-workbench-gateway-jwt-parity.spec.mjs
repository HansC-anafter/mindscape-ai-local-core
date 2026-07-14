import assert from 'node:assert/strict';
import http from 'node:http';
import net from 'node:net';
import test from 'node:test';

import { createFrontendProxyServer } from './frontend-proxy-server.mjs';
import {
  ACCESS_AUDIENCE,
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

test('singleton-array audience is accepted identically on HTTP and WebSocket', async (t) => {
  const upstream = http.createServer((_req, response) => {
    response.writeHead(200, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ ok: true }));
  });
  upstream.on('upgrade', (_req, socket) => {
    socket.end('HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n');
  });
  const upstreamPort = await listen(upstream);
  let resolverCalls = 0;
  const server = createFrontendProxyServer({
    ingressMode: 'remote',
    nextRunningRef: { current: true },
    nextProxyTarget: { hostname: '127.0.0.1', port: upstreamPort },
    getMobileWorkbenchGatewayConfig: () => createGatewayConfig(),
    verifyAccessToken: createTestVerifier(),
    policyResolver: async () => {
      resolverCalls += 1;
      return createPolicyResolution();
    },
  });
  const port = await listen(server);
  t.after(async () => {
    await close(server);
    await close(upstream);
  });
  const token = createSignedAccessJwt();
  const claims = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString('utf8'));
  assert.deepEqual(claims.aud, [ACCESS_AUDIENCE]);
  const path = '/workspaces/workspace-a/capability-ui-hosts/yogacoach';

  const response = await requestLoopback(`http://127.0.0.1:${port}${path}`, {
    headers: {
      host: 'remote-workbench.mindscapeai.app',
      'Cf-Access-Jwt-Assertion': token,
    },
  });
  assert.equal(response.status, 200);

  const upgradeOutput = await new Promise((resolve, reject) => {
    const socket = net.connect(port, '127.0.0.1', () => {
      socket.write(
        `GET ${path} HTTP/1.1\r\n`
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
  assert.match(upgradeOutput, /^HTTP\/1\.1 101 Switching Protocols/m);
  assert.equal(resolverCalls, 2);
});

test('non-exact audience is rejected identically on HTTP and WebSocket', async (t) => {
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
  t.after(async () => {
    server.closeAllConnections?.();
    await new Promise((resolve) => server.close(resolve));
  });
  const token = createSignedAccessJwt({ claims: { aud: [ACCESS_AUDIENCE, 'other'] } });
  const path = '/workspaces/workspace-a/capability-ui-hosts/yogacoach';

  const response = await requestLoopback(`http://127.0.0.1:${port}${path}`, {
    headers: {
      host: 'remote-workbench.mindscapeai.app',
      'Cf-Access-Jwt-Assertion': token,
    },
  });
  assert.equal(response.status, 403);
  assert.equal(response.headers.get('x-mindscape-remote-auth-stage'), 'identity_rejected');
  assert.equal(response.headers.get('x-mindscape-remote-auth-reason'), 'invalid_access_token_audience');

  const upgradeOutput = await new Promise((resolve, reject) => {
    const socket = net.connect(port, '127.0.0.1', () => {
      socket.write(
        `GET ${path} HTTP/1.1\r\n`
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
  assert.match(upgradeOutput, /X-Mindscape-Remote-Auth-Stage: identity_rejected/i);
  assert.match(upgradeOutput, /X-Mindscape-Remote-Auth-Reason: invalid_access_token_audience/i);
  assert.equal(resolverCalls, 0);
});

test('valid identity cannot use localhost Host on HTTP or WebSocket', async (t) => {
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
  t.after(async () => {
    server.closeAllConnections?.();
    await new Promise((resolve) => server.close(resolve));
  });
  const token = createSignedAccessJwt();
  const path = '/workspaces/workspace-a/capability-ui-hosts/yogacoach';

  const response = await requestLoopback(`http://127.0.0.1:${port}${path}`, {
    headers: {
      host: 'localhost:3001',
      'Cf-Access-Jwt-Assertion': token,
    },
  });
  assert.equal(response.status, 403);
  assert.equal(response.headers.get('x-mindscape-remote-auth-reason'), 'invalid_public_host');

  const output = await new Promise((resolve, reject) => {
    const socket = net.connect(port, '127.0.0.1', () => {
      socket.write(
        `GET ${path} HTTP/1.1\r\n`
        + 'Host: localhost:3001\r\n'
        + 'Connection: Upgrade\r\n'
        + 'Upgrade: websocket\r\n'
        + `Cf-Access-Jwt-Assertion: ${token}\r\n\r\n`,
      );
    });
    let raw = '';
    socket.setEncoding('utf8');
    socket.on('data', (chunk) => { raw += chunk; });
    socket.on('end', () => resolve(raw));
    socket.on('error', reject);
  });
  assert.match(output, /^HTTP\/1\.1 403 Forbidden/m);
  assert.match(output, /X-Mindscape-Remote-Auth-Reason: invalid_public_host/i);
  assert.equal(resolverCalls, 0);
});
