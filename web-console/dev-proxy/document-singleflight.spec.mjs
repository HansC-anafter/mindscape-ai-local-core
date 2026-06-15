import http from 'node:http';
import { afterEach, describe, expect, it } from 'vitest';

import {
  createFrontendDocumentSingleflight,
  isFrontendDocumentRequest,
  normalizeFrontendDocumentSingleflightKey,
} from './document-singleflight.mjs';
import {
  clearFrontendDocumentSingleflightForTests,
  createFrontendProxyServer,
} from '../dev-proxy.mjs';

describe('frontend document single-flight', () => {
  afterEach(() => {
    delete process.env.NEXT_DEV_HOST;
    delete process.env.NEXT_DEV_PORT;
  });

  it('classifies only document GET routes for Next dev single-flight', () => {
    expect(isFrontendDocumentRequest('GET', '/')).toBe(true);
    expect(isFrontendDocumentRequest('GET', '/workspaces/ws-1')).toBe(true);
    expect(isFrontendDocumentRequest('GET', '/workspaces/ws-1/capability-ui-hosts/ig?component=assets')).toBe(true);
    expect(isFrontendDocumentRequest('HEAD', '/workspaces/ws-1')).toBe(false);
    expect(isFrontendDocumentRequest('POST', '/workspaces/ws-1')).toBe(false);
    expect(isFrontendDocumentRequest('GET', '/api/v1/ig/references')).toBe(false);
    expect(isFrontendDocumentRequest('GET', '/_next/webpack-hmr')).toBe(false);
    expect(isFrontendDocumentRequest('GET', '/_next/static/chunks/app.js')).toBe(false);
    expect(isFrontendDocumentRequest('GET', '/favicon.ico')).toBe(false);
    expect(isFrontendDocumentRequest('GET', '/workspaces/ws-1/icon.png')).toBe(false);
  });

  it('keeps query-bearing document keys distinct', () => {
    expect(normalizeFrontendDocumentSingleflightKey('GET', '/workspaces/ws-1/capability-ui-hosts/ig?component=assets')).toBe(
      'GET:/workspaces/ws-1/capability-ui-hosts/ig?component=assets',
    );
    expect(normalizeFrontendDocumentSingleflightKey('GET', '/api/v1/ig/references')).toBeNull();
  });

  it('shares one producer for duplicate document routes', async () => {
    const gate = createFrontendDocumentSingleflight();
    let producerCount = 0;

    const first = gate.run('GET', '/workspaces/ws-1/capability-ui-hosts/ig', async () => {
      producerCount += 1;
      await new Promise((resolve) => setTimeout(resolve, 20));
      return { ok: true, producerCount };
    });
    const second = gate.run('GET', '/workspaces/ws-1/capability-ui-hosts/ig', async () => {
      producerCount += 1;
      return { ok: true, producerCount };
    });

    await expect(first.promise).resolves.toEqual({ ok: true, producerCount: 1 });
    await expect(second.promise).resolves.toEqual({ ok: true, producerCount: 1 });
    expect(first.shared).toBe(false);
    expect(second.shared).toBe(true);
    expect(producerCount).toBe(1);
    expect(gate.size).toBe(0);
  });

  it('proxies duplicate document GETs through one Next upstream without returning 429', async () => {
    let nextRequestCount = 0;
    const nextServer = await createTestServer((req, res) => {
      nextRequestCount += 1;
      setTimeout(() => {
        const body = `<html><body>${req.url}:${nextRequestCount}</body></html>`;
        res.writeHead(200, {
          'content-type': 'text/html; charset=utf-8',
          'cache-control': 'no-store',
          'content-length': Buffer.byteLength(body),
        });
        res.end(body);
      }, 30);
    });
    const nextAddress = nextServer.address();
    const nextPort = typeof nextAddress === 'object' && nextAddress ? nextAddress.port : null;
    process.env.NEXT_DEV_HOST = '127.0.0.1';
    process.env.NEXT_DEV_PORT = String(nextPort);
    clearFrontendDocumentSingleflightForTests();
    const proxy = createFrontendProxyServer({
      nextRunningRef: { current: true },
      nextProxyTarget: { hostname: '127.0.0.1', port: nextPort },
    });

    await new Promise((resolve) => proxy.listen(0, '127.0.0.1', resolve));
    const proxyAddress = proxy.address();
    const proxyPort = typeof proxyAddress === 'object' && proxyAddress ? proxyAddress.port : null;

    try {
      const target = `http://127.0.0.1:${proxyPort}/workspaces/ws-1/capability-ui-hosts/ig?component=assets`;
      const [first, second] = await Promise.all([fetch(target), fetch(target)]);
      const [firstBody, secondBody] = await Promise.all([first.text(), second.text()]);

      expect(first.status).toBe(200);
      expect(second.status).toBe(200);
      expect(first.status).not.toBe(429);
      expect(second.status).not.toBe(429);
      expect(firstBody).toBe(secondBody);
      expect(nextRequestCount).toBe(1);
    } finally {
      clearFrontendDocumentSingleflightForTests();
      await closeServer(proxy);
      await closeServer(nextServer);
    }
  });

  it('does not merge different document query keys', async () => {
    const gate = createFrontendDocumentSingleflight();
    let producerCount = 0;

    const first = gate.run('GET', '/workspaces/ws-1/capability-ui-hosts/ig?component=assets', async () => {
      producerCount += 1;
      return { producerCount };
    });
    const second = gate.run('GET', '/workspaces/ws-1/capability-ui-hosts/ig?component=produce', async () => {
      producerCount += 1;
      return { producerCount };
    });

    await Promise.all([first.promise, second.promise]);
    expect(first.shared).toBe(false);
    expect(second.shared).toBe(false);
    expect(producerCount).toBe(2);
  });
});

function createTestServer(handler) {
  return new Promise((resolve) => {
    const server = http.createServer(handler);
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

function closeServer(server) {
  return new Promise((resolve, reject) => {
    server.close((error) => {
      if (error) {
        reject(error);
        return;
      }
      resolve();
    });
  });
}
