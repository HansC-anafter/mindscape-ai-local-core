import http from 'node:http';
import { performance } from 'node:perf_hooks';
import {
  copyProxyRequestHeaders,
  copyProxyResponseHeaders,
} from './proxy-headers.mjs';

const DEV_API_READ_CACHE_MAX_BODY_BYTES = Number.parseInt(
  process.env.FRONTEND_PROXY_READ_CACHE_MAX_BODY_BYTES || String(1024 * 1024),
  10,
);
const devApiReadCache = new Map();
const devApiReadInflight = new Map();

export function clearDevApiReadCacheForTests() {
  devApiReadCache.clear();
  devApiReadInflight.clear();
}

export function resolveDevApiReadCacheTtlMs(requestUrl = '/', method = 'GET') {
  if (String(method || 'GET').toUpperCase() !== 'GET') {
    return 0;
  }

  try {
    const parsed = new URL(requestUrl, 'http://localhost');
    const { pathname } = parsed;
    if (pathname === '/api/v1/ig/workbench/sidebar-summary') {
      return 2_000;
    }
    if (pathname === '/api/v1/ig/browser-profiles') {
      return 5_000;
    }
    if (pathname === '/api/v1/cloud-sync/status') {
      return 2_000;
    }
    if (pathname === '/api/v1/mcp/agent/status') {
      return 2_000;
    }
    if (pathname === '/api/v1/system-settings/models') {
      return 10_000;
    }
    if (pathname === '/api/v1/settings/model-route-registry/workspace-executor') {
      return 5_000;
    }
    if (/^\/api\/v1\/workspaces\/[^/]+\/summary$/.test(pathname)) {
      return 2_000;
    }
    if (/^\/api\/v1\/workspaces\/[^/]+\/threads$/.test(pathname)) {
      return 2_000;
    }
    if (/^\/api\/v1\/workspaces\/[^/]+\/agents$/.test(pathname)) {
      return 5_000;
    }
    if (/^\/api\/v1\/workspaces\/[^/]+\/workbench$/.test(pathname)) {
      return 5_000;
    }
    if (/^\/api\/v1\/workspaces\/[^/]+\/intents$/.test(pathname)) {
      return 5_000;
    }
    if (/^\/api\/v1\/workspaces\/[^/]+\/events$/.test(pathname)) {
      return 2_000;
    }
    if (/^\/api\/v1\/workspaces\/[^/]+\/governance\/memory-health$/.test(pathname)) {
      return 5_000;
    }
    if (/^\/api\/v1\/workspaces\/[^/]+\/health$/.test(pathname)) {
      return 5_000;
    }
    if (/^\/api\/v1\/workspaces\/[^/]+\/executions\/[^/]+\/progress-snapshot$/.test(pathname)) {
      return 1_000;
    }
    if (/^\/api\/v1\/playbooks\/execute\/[^/]+\/status$/.test(pathname)) {
      return 1_000;
    }
  } catch {
    return 0;
  }

  return 0;
}

function devApiReadCacheKey(method, target) {
  return `${String(method || 'GET').toUpperCase()}:${target.hostname}:${target.port}:${target.path}`;
}

function writeBufferedProxyResponse(record, req, res) {
  if (res.destroyed || res.writableEnded) {
    return;
  }

  const headers = copyProxyResponseHeaders(record.headers, req.url, req.method, record.statusCode || 502);
  headers['content-length'] = String(record.body.length);
  try {
    res.writeHead(record.statusCode || 502, headers);
    res.end(record.body);
  } catch (error) {
    if (error?.code !== 'EPIPE' && error?.code !== 'ECONNRESET') {
      throw error;
    }
  }
}

function fetchBufferedDevApiResponse(req, target) {
  return new Promise((resolve, reject) => {
    const upstream = http.request(
      {
        hostname: target.hostname,
        port: target.port,
        method: req.method,
        path: target.path,
        headers: copyProxyRequestHeaders(req.headers, target),
      },
      (upstreamRes) => {
        const chunks = [];
        let totalBytes = 0;
        upstreamRes.on('data', (chunk) => {
          totalBytes += chunk.length;
          if (totalBytes <= DEV_API_READ_CACHE_MAX_BODY_BYTES) {
            chunks.push(chunk);
          }
        });
        upstreamRes.on('end', () => {
          if (totalBytes > DEV_API_READ_CACHE_MAX_BODY_BYTES) {
            reject(new Error('dev_api_read_cache_body_too_large'));
            return;
          }
          resolve({
            statusCode: upstreamRes.statusCode || 502,
            headers: upstreamRes.headers,
            body: Buffer.concat(chunks, totalBytes),
          });
        });
      },
    );

    upstream.on('error', reject);
    upstream.end();
  });
}

export function tryProxyCachedDevApiRead(req, res, target, logCompletion, markTerminalError = null) {
  const ttlMs = resolveDevApiReadCacheTtlMs(req.url, req.method);
  if (!ttlMs) {
    return false;
  }

  const key = devApiReadCacheKey(req.method, target);
  const now = performance.now();
  const cached = devApiReadCache.get(key);
  if (cached && cached.expiresAt > now) {
    writeBufferedProxyResponse(cached.record, req, res);
    logCompletion('cache_hit', { cache: 'hit', cache_ttl_ms: Math.round(cached.expiresAt - now) });
    return true;
  }

  let pending = devApiReadInflight.get(key);
  if (!pending) {
    pending = fetchBufferedDevApiResponse(req, target)
      .then((record) => {
        if (record.statusCode >= 200 && record.statusCode < 300) {
          devApiReadCache.set(key, {
            expiresAt: performance.now() + ttlMs,
            record,
          });
        }
        return record;
      })
      .finally(() => {
        devApiReadInflight.delete(key);
      });
    devApiReadInflight.set(key, pending);
  }

  pending
    .then((record) => {
      writeBufferedProxyResponse(record, req, res);
    })
    .catch((error) => {
      if (typeof markTerminalError === 'function') {
        markTerminalError(error?.code || error?.message || 'unknown');
      }
      if (!res.headersSent) {
        res.writeHead(502, { 'content-type': 'application/json', 'cache-control': 'no-store' });
      }
      res.end(JSON.stringify({ error: 'backend_dev_proxy_unavailable' }));
    });
  return true;
}
