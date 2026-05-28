import http from 'node:http';
import net from 'node:net';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { performance } from 'node:perf_hooks';
import { fileURLToPath } from 'node:url';
import {
  prewarmNextDevRoutes,
} from './dev-proxy/prewarm.mjs';
import { resolveApiRoutePlane } from './dev-proxy/api-route-plane.mjs';

export { resolveFrontendPrewarmPaths } from './dev-proxy/prewarm.mjs';
export { resolveApiRoutePlane } from './dev-proxy/api-route-plane.mjs';

const PUBLIC_HOST = process.env.FRONTEND_PROXY_HOST || '0.0.0.0';
const PUBLIC_PORT = Number.parseInt(process.env.PORT || '3000', 10);
const NEXT_HOST = process.env.NEXT_DEV_HOST || '127.0.0.1';
const NEXT_PORT = Number.parseInt(process.env.NEXT_DEV_PORT || '3001', 10);
const PROXY_LOG_MODE = process.env.FRONTEND_PROXY_LOG_MODE || 'slow';
const PROXY_SLOW_LOG_THRESHOLD_MS = Number.parseInt(
  process.env.FRONTEND_PROXY_SLOW_LOG_THRESHOLD_MS || '1000',
  10,
);
const PREWARM_ENABLED = process.env.FRONTEND_PREWARM_ENABLED === '1';
const PREWARM_DELAY_MS = Number.parseInt(process.env.FRONTEND_PREWARM_DELAY_MS || '8000', 10);
const NEXT_DEV_TURBO_ENABLED = process.env.NEXT_DEV_TURBO === '1';
const HOP_BY_HOP_HEADERS = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
]);
const DEV_API_READ_CACHE_MAX_BODY_BYTES = Number.parseInt(
  process.env.FRONTEND_PROXY_READ_CACHE_MAX_BODY_BYTES || String(1024 * 1024),
  10,
);
const devApiReadCache = new Map();
const devApiReadInflight = new Map();
const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));
const SERVICE_ENDPOINT_SEED_PATHS = [
  process.env.MINDSCAPE_SERVICE_ENDPOINT_SEED,
  '/app/config/service-endpoints.seed.json',
  path.resolve(MODULE_DIR, '../config/service-endpoints.seed.json'),
].filter(Boolean);
let requestSequence = 0;
let serviceEndpointSeedCache = null;

function loadServiceEndpointSeed() {
  if (serviceEndpointSeedCache) {
    return serviceEndpointSeedCache;
  }
  for (const candidate of SERVICE_ENDPOINT_SEED_PATHS) {
    try {
      serviceEndpointSeedCache = JSON.parse(fs.readFileSync(candidate, 'utf8'));
      return serviceEndpointSeedCache;
    } catch {
      // Try the next candidate.
    }
  }
  serviceEndpointSeedCache = { endpoints: [] };
  return serviceEndpointSeedCache;
}

function resolveSeedEndpointUrl(serviceId, audience) {
  const seed = loadServiceEndpointSeed();
  const endpoint = Array.isArray(seed.endpoints)
    ? seed.endpoints.find((item) => item?.service_id === serviceId && item?.audience === audience)
    : null;
  return String(endpoint?.url || '').trim();
}

export function isFrontendLivenessPath(requestUrl = '/') {
  try {
    const parsed = new URL(requestUrl, 'http://localhost');
    return parsed.pathname === '/healthz' || parsed.pathname === '/api/healthz';
  } catch {
    return requestUrl === '/healthz' || requestUrl === '/api/healthz';
  }
}

function normalizeBaseUrl(value, fallback) {
  const resolved = String(value || '').trim() || fallback;
  return resolved.replace(/\/+$/, '');
}

export function isDevApiProxyPath(requestUrl = '/') {
  try {
    const parsed = new URL(requestUrl, 'http://localhost');
    return parsed.pathname.startsWith('/api/') && !isFrontendLivenessPath(requestUrl);
  } catch {
    return String(requestUrl || '').startsWith('/api/') && !isFrontendLivenessPath(requestUrl);
  }
}

export function resolveDevApiProxyTarget(requestUrl = '/') {
  const parsed = new URL(requestUrl, 'http://localhost');
  const routePlane = resolveApiRoutePlane(requestUrl);
  const registryMediaProxyUrl = resolveSeedEndpointUrl('local_core.media_proxy', 'container_internal');
  const registryControlBackendUrl =
    resolveSeedEndpointUrl('local_core.control_api', 'server_internal') ||
    resolveSeedEndpointUrl('local_core.control_api', 'container_internal');
  const registryExecutionBackendUrl =
    resolveSeedEndpointUrl('local_core.execution_api', 'server_internal') ||
    resolveSeedEndpointUrl('local_core.execution_api', 'container_internal');
  const baseUrl = routePlane.plane === 'media'
    ? normalizeBaseUrl(process.env.MEDIA_PROXY_URL, registryMediaProxyUrl)
    : normalizeBaseUrl(
        routePlane.plane === 'control'
          ? process.env.WEB_CONSOLE_CONTROL_BACKEND_URL ||
              process.env.WEB_CONSOLE_BACKEND_URL ||
              process.env.BACKEND_URL ||
              process.env.NEXT_PUBLIC_BACKEND_URL
          : process.env.WEB_CONSOLE_EXECUTION_BACKEND_URL ||
              process.env.WEB_CONSOLE_BACKEND_EXECUTION_URL,
        routePlane.plane === 'control' ? registryControlBackendUrl : registryExecutionBackendUrl,
      );
  const upstream = new URL(baseUrl);
  return {
    hostname: upstream.hostname,
    port: Number.parseInt(upstream.port || (upstream.protocol === 'https:' ? '443' : '80'), 10),
    protocol: upstream.protocol,
    path: `${parsed.pathname}${parsed.search}`,
    plane: routePlane.plane,
    plane_reason: routePlane.reason,
  };
}

function copyProxyRequestHeaders(headers, target) {
  const nextHeaders = {};
  for (const [key, value] of Object.entries(headers || {})) {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase()) && key.toLowerCase() !== 'host') {
      nextHeaders[key] = value;
    }
  }
  nextHeaders.host = target.port ? `${target.hostname}:${target.port}` : target.hostname;
  nextHeaders['x-mindscape-web-console-proxy'] = '1';
  return nextHeaders;
}

function shouldPreserveDevApiCacheControl(requestUrl = '/', method = 'GET') {
  if (method !== 'GET' && method !== 'HEAD') {
    return false;
  }

  try {
    const parsed = new URL(requestUrl, 'http://localhost');
    return (
      parsed.pathname.startsWith('/api/v1/media/') ||
      /^\/api\/v1\/ig\/references\/[^/]+\/image$/.test(parsed.pathname)
    );
  } catch {
    return false;
  }
}

export function copyProxyResponseHeaders(headers, requestUrl = '/', method = 'GET', statusCode = 200) {
  const nextHeaders = {};
  for (const [key, value] of Object.entries(headers || {})) {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
      nextHeaders[key] = value;
    }
  }
  const canCacheResponse = (statusCode >= 200 && statusCode < 300) || statusCode === 304;
  if (!canCacheResponse || !shouldPreserveDevApiCacheControl(requestUrl, method)) {
    nextHeaders['cache-control'] = 'no-store';
  } else if (!nextHeaders['cache-control']) {
    nextHeaders['cache-control'] = 'public, max-age=86400, immutable';
  }
  return nextHeaders;
}

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

function tryProxyCachedDevApiRead(req, res, target, logCompletion) {
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
      writeProxyTimingLog({
        event: 'upstream_error',
        method: req.method,
        path: normalizeProxyLogPath(req.url),
        upstream: 'backend_api',
        duration_ms: 0,
        error: error?.code || error?.message || 'unknown',
      });
      if (!res.headersSent) {
        res.writeHead(502, { 'content-type': 'application/json', 'cache-control': 'no-store' });
      }
      res.end(JSON.stringify({ error: 'backend_dev_proxy_unavailable' }));
    });
  return true;
}

function writeFrontendLiveness(res, nextRunning) {
  const statusCode = nextRunning ? 200 : 500;
  const body = JSON.stringify({
    status: nextRunning ? 'ok' : 'next_dev_unavailable',
    service: 'frontend',
    next_dev: nextRunning ? 'running' : 'exited',
  });

  res.writeHead(statusCode, {
    'content-type': 'application/json',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(body),
  });
  res.end(body);
}

export function computeNextDevRestartDelayMs(restartCount) {
  const boundedCount = Math.max(0, Math.min(Number(restartCount) || 0, 5));
  return Math.min(30_000, 1_000 * (2 ** boundedCount));
}

export function normalizeProxyLogPath(requestUrl = '/') {
  try {
    return new URL(requestUrl, 'http://localhost').pathname;
  } catch {
    const value = String(requestUrl || '/');
    return value.split('?')[0] || '/';
  }
}

export function classifyProxyUpstream(requestUrl = '/') {
  if (isDevApiProxyPath(requestUrl)) {
    const routePlane = resolveApiRoutePlane(requestUrl);
    if (routePlane.plane === 'media') {
      return 'media_proxy';
    }
    return routePlane.plane === 'control'
      ? 'backend_control_api'
      : 'backend_execution_api';
  }
  return 'next_dev';
}

function roundedDurationMs(startedAt) {
  return Math.round((performance.now() - startedAt) * 100) / 100;
}

export function resolveNextDevArgs(
  host = NEXT_HOST,
  port = NEXT_PORT,
  turboEnabled = NEXT_DEV_TURBO_ENABLED,
) {
  return [
    'exec',
    'next',
    'dev',
    ...(turboEnabled ? ['--turbo'] : []),
    '-H',
    host,
    '-p',
    String(port),
  ];
}

export function shouldWriteProxyTimingLog(
  event,
  logMode = PROXY_LOG_MODE,
  slowThresholdMs = PROXY_SLOW_LOG_THRESHOLD_MS,
) {
  if (logMode === 'none') {
    return false;
  }
  if (logMode === 'all') {
    return true;
  }
  if (!event || event.event === 'start') {
    return false;
  }
  if (event.event === 'upstream_error') {
    return true;
  }
  if (Number(event.status) >= 500 || Number(event.upstream_status) >= 500) {
    return true;
  }
  if (event.event === 'client_aborted' || event.event === 'client_closed') {
    return true;
  }
  return Number(event.duration_ms || 0) >= slowThresholdMs;
}

function writeProxyTimingLog(event) {
  if (!shouldWriteProxyTimingLog(event)) {
    return;
  }
  try {
    console.log(`[frontend-proxy] request ${JSON.stringify(event)}`);
  } catch (error) {
    if (error?.code !== 'EPIPE') {
      throw error;
    }
  }
}

function resolveNextProxyTarget(requestUrl = '/') {
  return {
    hostname: NEXT_HOST,
    port: NEXT_PORT,
    protocol: 'http:',
    path: requestUrl,
  };
}

function proxyHttpRequest(req, res) {
  const requestId = ++requestSequence;
  const startedAt = performance.now();
  const upstreamKind = classifyProxyUpstream(req.url);
  const logPath = normalizeProxyLogPath(req.url);
  let upstreamStatus = null;
  let upstreamHeaderMs = null;
  let completionLogged = false;
  const target = upstreamKind.startsWith('backend_') || upstreamKind === 'media_proxy'
    ? resolveDevApiProxyTarget(req.url)
    : resolveNextProxyTarget(req.url);

  writeProxyTimingLog({
    event: 'start',
    id: requestId,
    method: req.method,
    path: logPath,
    upstream: upstreamKind,
  });

  const logCompletion = (event, extra = {}) => {
    if (completionLogged) {
      return;
    }
    completionLogged = true;
    writeProxyTimingLog({
      event,
      id: requestId,
      method: req.method,
      path: logPath,
      upstream: upstreamKind,
      status: res.statusCode || upstreamStatus,
      upstream_status: upstreamStatus,
      upstream_header_ms: upstreamHeaderMs,
      duration_ms: roundedDurationMs(startedAt),
      ...extra,
    });
  };

  req.on('aborted', () => {
    logCompletion('client_aborted');
  });
  req.on('error', (error) => {
    logCompletion('client_closed', { error: error?.code || error?.message || 'request_error' });
  });
  res.on('error', (error) => {
    logCompletion('client_closed', { error: error?.code || error?.message || 'response_error' });
  });

  res.on('finish', () => {
    logCompletion('finish');
  });

  res.on('close', () => {
    if (!res.writableEnded) {
      logCompletion('client_closed');
    }
  });

  if (upstreamKind === 'backend_execution_api' && tryProxyCachedDevApiRead(req, res, target, logCompletion)) {
    return;
  }

  const upstream = http.request(
    {
      hostname: target.hostname,
      port: target.port,
      method: req.method,
      path: target.path,
      headers: copyProxyRequestHeaders(req.headers, target),
    },
    (upstreamRes) => {
      upstreamStatus = upstreamRes.statusCode || null;
      upstreamHeaderMs = roundedDurationMs(startedAt);
      res.writeHead(
        upstreamRes.statusCode || 502,
        copyProxyResponseHeaders(upstreamRes.headers, req.url, req.method, upstreamRes.statusCode || 502),
      );
      upstreamRes.on('error', (error) => {
        logCompletion('upstream_error', { error: error?.code || error?.message || 'upstream_response_error' });
        if (!res.destroyed) {
          res.destroy(error);
        }
      });
      upstreamRes.pipe(res);
    },
  );
  res.on('close', () => {
    if (!upstream.destroyed) {
      upstream.destroy();
    }
  });

  upstream.on('error', (error) => {
    writeProxyTimingLog({
      event: 'upstream_error',
      id: requestId,
      method: req.method,
      path: logPath,
      upstream: upstreamKind,
      duration_ms: roundedDurationMs(startedAt),
      error: error?.code || error?.message || 'unknown',
    });
    if (!res.headersSent) {
      res.writeHead(502, { 'content-type': 'application/json', 'cache-control': 'no-store' });
    }
    if (!res.destroyed && !res.writableEnded) {
      res.end(JSON.stringify({ error: isDevApiProxyPath(req.url) ? 'backend_dev_proxy_unavailable' : 'next_dev_proxy_unavailable' }));
    }
  });

  req.pipe(upstream);
}

function proxyUpgrade(req, socket, head) {
  const target = isDevApiProxyPath(req.url)
    ? resolveDevApiProxyTarget(req.url)
    : resolveNextProxyTarget(req.url);
  const upstream = net.connect(target.port, target.hostname, () => {
    const headers = copyProxyRequestHeaders(req.headers, target);
    upstream.write(
      `${req.method} ${target.path} HTTP/${req.httpVersion}\r\n` +
      Object.entries(headers)
        .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`)
        .join('\r\n') +
      '\r\n\r\n',
    );
    if (head?.length) {
      upstream.write(head);
    }
    socket.pipe(upstream).pipe(socket);
  });

  upstream.on('error', () => {
    socket.destroy();
  });
  socket.on('error', () => {
    upstream.destroy();
  });
}

export function createFrontendProxyServer({ nextRunningRef }) {
  const server = http.createServer((req, res) => {
    if (isFrontendLivenessPath(req.url)) {
      writeFrontendLiveness(res, nextRunningRef.current);
      return;
    }

    proxyHttpRequest(req, res);
  });

  server.on('upgrade', proxyUpgrade);
  server.on('clientError', (_error, socket) => {
    socket.end('HTTP/1.1 400 Bad Request\r\n\r\n');
  });

  return server;
}

export function start() {
  const nextRunningRef = { current: false };
  let nextProcess = null;
  let restartTimer = null;
  let prewarmTimer = null;
  let restartCount = 0;
  let shuttingDown = false;
  const server = createFrontendProxyServer({ nextRunningRef });

  const launchNextDev = () => {
    if (shuttingDown) {
      return;
    }

    nextRunningRef.current = false;
    nextProcess = spawn(
      'pnpm',
      resolveNextDevArgs(),
      {
        cwd: process.cwd(),
        env: process.env,
        stdio: 'inherit',
      },
    );

    nextProcess.on('spawn', () => {
      nextRunningRef.current = true;
      if (PREWARM_ENABLED) {
        prewarmTimer = setTimeout(() => {
          prewarmTimer = null;
          void prewarmNextDevRoutes();
        }, PREWARM_DELAY_MS);
      }
    });

    nextProcess.on('exit', (code, signal) => {
      nextRunningRef.current = false;
      if (prewarmTimer) {
        clearTimeout(prewarmTimer);
        prewarmTimer = null;
      }
      console.error(`[frontend-proxy] next dev exited code=${code ?? 'null'} signal=${signal ?? 'null'}`);

      if (shuttingDown) {
        return;
      }

      const delayMs = computeNextDevRestartDelayMs(restartCount);
      restartCount += 1;
      console.error(`[frontend-proxy] restarting next dev in ${delayMs}ms`);
      restartTimer = setTimeout(() => {
        restartTimer = null;
        launchNextDev();
      }, delayMs);
    });
  };

  launchNextDev();

  server.listen(PUBLIC_PORT, PUBLIC_HOST, () => {
    console.log(`[frontend-proxy] listening on ${PUBLIC_HOST}:${PUBLIC_PORT}, proxying to ${NEXT_HOST}:${NEXT_PORT}`);
  });

  const shutdown = () => {
    shuttingDown = true;
    if (restartTimer) {
      clearTimeout(restartTimer);
      restartTimer = null;
    }
    if (prewarmTimer) {
      clearTimeout(prewarmTimer);
      prewarmTimer = null;
    }
    server.close(() => {
      nextProcess?.kill('SIGTERM');
    });
    setTimeout(() => {
      nextProcess?.kill('SIGKILL');
      process.exit(0);
    }, 10_000).unref();
  };

  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  start();
}
