import http from 'node:http';
import net from 'node:net';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { performance } from 'node:perf_hooks';
import { fileURLToPath } from 'node:url';
import {
  prewarmNextDevRoutes,
} from './dev-proxy/prewarm.mjs';
import { resolveApiRoutePlane } from './dev-proxy/api-route-plane.mjs';
import {
  DEFAULT_FRONTEND_DOCUMENT_SINGLEFLIGHT_MAX_BODY_BYTES,
  isFrontendDocumentRequest,
  normalizeFrontendDocumentSingleflightKey,
} from './dev-proxy/document-singleflight.mjs';
import {
  isFrontendDocumentHeadReadinessRequest,
  writeFrontendDocumentHeadReadiness,
} from './dev-proxy/head-readiness.mjs';
import {
  resolveDeviceLinkHttpsConfig,
  startDeviceLinkHttpsProxy,
} from './dev-proxy/device-link-https.mjs';
import {
  isMobileWorkbenchGatewayPathAllowed,
  isMobileWorkbenchGatewayRequestAllowed,
  isMobileWorkbenchGatewayRequestAllowedAsync,
  isLoopbackControlPlaneRequest,
  formatMobileWorkbenchGatewayConfig,
  resolveMobileWorkbenchGatewayConfig,
} from './dev-proxy/mobile-workbench-gateway.mjs';
import {
  createMobileWorkbenchGatewayPolicyResolver,
} from './dev-proxy/mobile-workbench-gateway-policy-resolver.mjs';
import {
  createRemoteWorkbenchObservability,
  DEFAULT_AUDIT_LIMIT,
} from './dev-proxy/remote-workbench-observability.mjs';

export { resolveFrontendPrewarmPaths } from './dev-proxy/prewarm.mjs';
export { resolveApiRoutePlane } from './dev-proxy/api-route-plane.mjs';
export {
  DEFAULT_FRONTEND_DOCUMENT_SINGLEFLIGHT_MAX_BODY_BYTES,
  createFrontendDocumentSingleflight,
  isFrontendDocumentRequest,
  normalizeFrontendDocumentSingleflightKey,
} from './dev-proxy/document-singleflight.mjs';
export {
  isFrontendDocumentHeadReadinessRequest,
  writeFrontendDocumentHeadReadiness,
} from './dev-proxy/head-readiness.mjs';
export {
  isAllowedDeviceLinkHttpsPath,
  isDeviceLinkHttpsReadinessPath,
  resolveDeviceLinkHttpsConfig,
  startDeviceLinkHttpsProxy,
} from './dev-proxy/device-link-https.mjs';
export {
  isMobileWorkbenchGatewayPathAllowed,
  isMobileWorkbenchGatewayRequestAllowed,
  isMobileWorkbenchGatewayRequestAllowedAsync,
  isLoopbackControlPlaneRequest,
  formatMobileWorkbenchGatewayConfig,
  resolveMobileWorkbenchGatewayConfig,
} from './dev-proxy/mobile-workbench-gateway.mjs';
export {
  createRemoteWorkbenchObservability,
} from './dev-proxy/remote-workbench-observability.mjs';

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
const FRONTEND_DOCUMENT_SINGLEFLIGHT_MAX_BODY_BYTES = Number.parseInt(
  process.env.FRONTEND_DOCUMENT_SINGLEFLIGHT_MAX_BODY_BYTES
    || String(DEFAULT_FRONTEND_DOCUMENT_SINGLEFLIGHT_MAX_BODY_BYTES),
  10,
);
const devApiReadCache = new Map();
const devApiReadInflight = new Map();
const frontendDocumentStreamInflight = new Map();
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

function buildInternalApiUrl(requestPath = '/') {
  const target = resolveDevApiProxyTarget(requestPath);
  const port = target.port ? `:${target.port}` : '';
  return `${target.protocol}//${target.hostname}${port}${target.path}`;
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

export function copyProxyUpgradeHeaders(headers, target) {
  const nextHeaders = copyProxyRequestHeaders(headers, target);
  const upgradeHeader = headers?.upgrade;
  nextHeaders.connection = 'Upgrade';
  nextHeaders.upgrade = Array.isArray(upgradeHeader)
    ? upgradeHeader[0] || 'websocket'
    : upgradeHeader || 'websocket';
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
      /^\/api\/v1\/capability-packs\/installed-capabilities\/[^/]+\/ui-assets\/.+/.test(parsed.pathname) ||
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

export function clearFrontendDocumentSingleflightForTests() {
  frontendDocumentStreamInflight.clear();
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

function tryProxyCachedDevApiRead(req, res, target, logCompletion, markTerminalError = null) {
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

function writeFrontendDocumentSubscriberError(subscriber, errorCode) {
  if (typeof subscriber.markTerminalError === 'function') {
    subscriber.markTerminalError(errorCode);
  }
  if (!subscriber.res.headersSent) {
    subscriber.res.writeHead(502, { 'content-type': 'application/json', 'cache-control': 'no-store' });
  }
  if (!subscriber.res.destroyed && !subscriber.res.writableEnded) {
    subscriber.res.end(JSON.stringify({ error: 'next_dev_proxy_unavailable' }));
  }
}

function writeFrontendDocumentSubscriberHeaders(flight, subscriber) {
  if (!flight.headers || subscriber.res.headersSent || subscriber.res.destroyed || subscriber.res.writableEnded) {
    return;
  }
  subscriber.res.writeHead(
    flight.statusCode || 502,
    copyProxyResponseHeaders(flight.headers, subscriber.req.url, subscriber.req.method, flight.statusCode || 502),
  );
}

function writeFrontendDocumentSubscriberChunk(subscriber, chunk) {
  if (subscriber.res.destroyed || subscriber.res.writableEnded) {
    return;
  }
  try {
    subscriber.res.write(chunk);
  } catch (error) {
    if (error?.code !== 'EPIPE' && error?.code !== 'ECONNRESET') {
      throw error;
    }
  }
}

function endFrontendDocumentSubscriber(subscriber) {
  if (subscriber.res.destroyed || subscriber.res.writableEnded) {
    return;
  }
  try {
    subscriber.res.end();
    subscriber.logCompletion('finish', {
      document_singleflight: subscriber.shared ? 'shared' : 'origin',
    });
  } catch (error) {
    if (error?.code !== 'EPIPE' && error?.code !== 'ECONNRESET') {
      throw error;
    }
  }
}

function attachFrontendDocumentSubscriber(flight, subscriber) {
  flight.subscribers.add(subscriber);
  const detach = () => {
    flight.subscribers.delete(subscriber);
  };
  subscriber.res.on('close', detach);

  if (flight.errorCode) {
    writeFrontendDocumentSubscriberError(subscriber, flight.errorCode);
    return;
  }

  if (flight.headers) {
    writeFrontendDocumentSubscriberHeaders(flight, subscriber);
    if (flight.replayable) {
      for (const chunk of flight.chunks) {
        writeFrontendDocumentSubscriberChunk(subscriber, chunk);
      }
    } else if (subscriber.shared) {
      writeFrontendDocumentSubscriberError(subscriber, 'frontend_document_singleflight_replay_unavailable');
      return;
    }
  }

  if (flight.ended) {
    endFrontendDocumentSubscriber(subscriber);
  }
}

function failFrontendDocumentFlight(flight, key, errorCode) {
  flight.errorCode = errorCode;
  frontendDocumentStreamInflight.delete(key);
  for (const subscriber of Array.from(flight.subscribers)) {
    writeFrontendDocumentSubscriberError(subscriber, errorCode);
  }
  flight.subscribers.clear();
}

function startFrontendDocumentFlight(req, target, key) {
  const flight = {
    chunks: [],
    ended: false,
    errorCode: null,
    headers: null,
    replayable: true,
    statusCode: null,
    subscribers: new Set(),
    totalBytes: 0,
  };
  frontendDocumentStreamInflight.set(key, flight);

  const upstream = http.request(
    {
      hostname: target.hostname,
      port: target.port,
      method: 'GET',
      path: target.path,
      headers: copyProxyRequestHeaders(req.headers, target),
    },
    (upstreamRes) => {
      flight.statusCode = upstreamRes.statusCode || 502;
      flight.headers = upstreamRes.headers;
      for (const subscriber of Array.from(flight.subscribers)) {
        writeFrontendDocumentSubscriberHeaders(flight, subscriber);
      }
      upstreamRes.on('data', (chunk) => {
        flight.totalBytes += chunk.length;
        if (flight.totalBytes <= FRONTEND_DOCUMENT_SINGLEFLIGHT_MAX_BODY_BYTES && flight.replayable) {
          flight.chunks.push(Buffer.from(chunk));
        } else {
          flight.replayable = false;
          flight.chunks.length = 0;
        }
        for (const subscriber of Array.from(flight.subscribers)) {
          writeFrontendDocumentSubscriberChunk(subscriber, chunk);
        }
      });
      upstreamRes.on('end', () => {
        flight.ended = true;
        frontendDocumentStreamInflight.delete(key);
        for (const subscriber of Array.from(flight.subscribers)) {
          endFrontendDocumentSubscriber(subscriber);
        }
        flight.subscribers.clear();
      });
      upstreamRes.on('error', (error) => {
        failFrontendDocumentFlight(
          flight,
          key,
          error?.code || error?.message || 'upstream_response_error',
        );
      });
    },
  );

  upstream.on('error', (error) => {
    failFrontendDocumentFlight(flight, key, error?.code || error?.message || 'unknown');
  });
  upstream.end();
  return flight;
}

function tryProxySingleflightNextDocument(req, res, target, logCompletion, markTerminalError = null) {
  const key = normalizeFrontendDocumentSingleflightKey(req.method, req.url);
  if (!key || !isFrontendDocumentRequest(req.method, req.url)) {
    return false;
  }

  let flight = frontendDocumentStreamInflight.get(key);
  const shared = Boolean(flight);
  if (!flight) {
    flight = startFrontendDocumentFlight(req, target, key);
  }
  attachFrontendDocumentSubscriber(flight, {
    logCompletion,
    markTerminalError,
    req,
    res,
    shared,
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

function isMobileWorkbenchGatewayHealthRequest(requestUrl = '/', method = 'GET') {
  if (String(method || 'GET').toUpperCase() !== 'GET') {
    return false;
  }

  try {
    const parsed = new URL(requestUrl, 'http://localhost');
    return parsed.pathname === '/api/v1/host/services/mobile-workbench-gateway/health';
  } catch {
    return String(requestUrl || '') === '/api/v1/host/services/mobile-workbench-gateway/health';
  }
}

function isMobileWorkbenchGatewaySummaryRequest(requestUrl = '/', method = 'GET') {
  if (String(method || 'GET').toUpperCase() !== 'GET') {
    return false;
  }

  try {
    const parsed = new URL(requestUrl, 'http://localhost');
    return parsed.pathname === '/api/v1/host/services/mobile-workbench-gateway/summary';
  } catch {
    return String(requestUrl || '') === '/api/v1/host/services/mobile-workbench-gateway/summary';
  }
}

function isMobileWorkbenchGatewayAuditRequest(requestUrl = '/', method = 'GET') {
  if (String(method || 'GET').toUpperCase() !== 'GET') {
    return false;
  }

  try {
    const parsed = new URL(requestUrl, 'http://localhost');
    return parsed.pathname === '/api/v1/host/services/mobile-workbench-gateway/audit';
  } catch {
    return String(requestUrl || '') === '/api/v1/host/services/mobile-workbench-gateway/audit';
  }
}

export function isDeviceLinkHttpsHealthRequest(requestUrl = '/', method = 'GET') {
  if (String(method || 'GET').toUpperCase() !== 'GET') {
    return false;
  }

  try {
    const parsed = new URL(requestUrl, 'http://localhost');
    return parsed.pathname === '/api/v1/host/services/device-link-https/health';
  } catch {
    return String(requestUrl || '') === '/api/v1/host/services/device-link-https/health';
  }
}

export function writeDeviceLinkHttpsHealth(res, config = resolveDeviceLinkHttpsConfig()) {
  const body = JSON.stringify({
    status: config.enabled ? 'ok' : 'disabled',
    service: 'device-link-https',
    enabled: config.enabled,
    reason: config.reason,
    errors: [...(config.errors || [])],
    public_origin: config.publicOrigin || null,
    host: config.host,
    port: config.port,
  });

  res.writeHead(200, {
    'content-type': 'application/json',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(body),
  });
  res.end(body);
}

function writeMobileWorkbenchGatewayHealth(res, config = resolveMobileWorkbenchGatewayConfig()) {
  const formatted = formatMobileWorkbenchGatewayConfig(config);
  const statusCode = 200;
  const body = JSON.stringify({
    status: config.enabled ? 'ok' : 'disabled',
    service: 'mobile-workbench-gateway',
    enabled: config.enabled,
    reason: config.reason,
    errors: [...(config.errors || [])],
    gateway: formatted,
  });

  res.writeHead(statusCode, {
    'content-type': 'application/json',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(body),
  });
  res.end(body);
}

function parseMobileWorkbenchGatewayReadQuery(requestUrl = '/') {
  const parsed = new URL(requestUrl, 'http://localhost');
  const workspaceId = String(parsed.searchParams.get('workspace_id') || '').trim() || null;
  const capabilityCode = String(parsed.searchParams.get('capability_code') || '').trim() || null;
  const originType = String(parsed.searchParams.get('origin_type') || 'public_host').trim() || 'public_host';
  const limitValue = parsed.searchParams.get('limit');
  const limit = limitValue === null ? DEFAULT_AUDIT_LIMIT : Number.parseInt(limitValue, 10);
  return {
    workspaceId,
    capabilityCode,
    originType,
    limit,
  };
}

async function writeMobileWorkbenchGatewaySummary(res, remoteWorkbenchObservability, requestUrl = '/') {
  const query = parseMobileWorkbenchGatewayReadQuery(requestUrl);
  const body = JSON.stringify(await remoteWorkbenchObservability.readSummary({
    workspaceId: query.workspaceId,
    capabilityCode: query.capabilityCode,
    originType: query.originType,
  }));
  res.writeHead(200, {
    'content-type': 'application/json',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(body),
  });
  res.end(body);
}

async function writeMobileWorkbenchGatewayAudit(res, remoteWorkbenchObservability, requestUrl = '/') {
  const query = parseMobileWorkbenchGatewayReadQuery(requestUrl);
  const body = JSON.stringify(await remoteWorkbenchObservability.readAuditTail({
    workspaceId: query.workspaceId,
    capabilityCode: query.capabilityCode,
    originType: query.originType,
    limit: query.limit,
  }));
  res.writeHead(200, {
    'content-type': 'application/json',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(body),
  });
  res.end(body);
}

function writeMobileWorkbenchGatewayRejection(res, requestResult = {}, requestUrl = '/') {
  const reason = String(requestResult?.reason || 'mobile_workbench_gateway_access_denied');
  const path = requestUrl;
  const statusCode = Number(requestResult?.status_code) === 403 ? 403 : 404;
  const body = JSON.stringify({
    error: reason,
    path,
    reason_code: requestResult.reason_code || undefined,
    context: requestResult.context || undefined,
  });
  res.writeHead(statusCode, {
    'content-type': 'application/json',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(body),
  });
  res.end(body);
  return {
    statusCode,
    bodyBytes: Buffer.byteLength(body),
  };
}

export function computeNextDevRestartDelayMs(restartCount) {
  const boundedCount = Math.max(0, Math.min(Number(restartCount) || 0, 5));
  return Math.min(30_000, 1_000 * (2 ** boundedCount));
}

export function createDeviceLinkIngressToken() {
  return crypto.randomBytes(32).toString('hex');
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

function resolveChunkByteLength(chunk, encoding) {
  if (chunk === undefined || chunk === null) {
    return 0;
  }
  if (typeof chunk === 'string') {
    return Buffer.byteLength(chunk, typeof encoding === 'string' ? encoding : 'utf8');
  }
  if (Buffer.isBuffer(chunk)) {
    return chunk.length;
  }
  if (ArrayBuffer.isView(chunk)) {
    return chunk.byteLength;
  }
  if (chunk instanceof ArrayBuffer) {
    return chunk.byteLength;
  }
  return 0;
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

function resolveNextProxyTarget(requestUrl = '/', nextProxyTarget = null) {
  return {
    hostname: nextProxyTarget?.hostname || NEXT_HOST,
    port: nextProxyTarget?.port || NEXT_PORT,
    protocol: 'http:',
    path: requestUrl,
  };
}

function proxyHttpRequest(req, res, { requestId = ++requestSequence, onComplete = null, nextProxyTarget = null } = {}) {
  const startedAt = performance.now();
  const upstreamKind = classifyProxyUpstream(req.url);
  const logPath = normalizeProxyLogPath(req.url);
  let upstreamStatus = null;
  let upstreamHeaderMs = null;
  let completionLogged = false;
  let responseBytes = 0;
  let terminalEvent = 'finish';
  let terminalError = null;
  const target = upstreamKind.startsWith('backend_') || upstreamKind === 'media_proxy'
    ? resolveDevApiProxyTarget(req.url)
    : resolveNextProxyTarget(req.url, nextProxyTarget);

  const originalWrite = res.write.bind(res);
  const originalEnd = res.end.bind(res);
  res.write = function patchedWrite(chunk, encoding, callback) {
    responseBytes += resolveChunkByteLength(chunk, encoding);
    return originalWrite(chunk, encoding, callback);
  };
  res.end = function patchedEnd(chunk, encoding, callback) {
    responseBytes += resolveChunkByteLength(chunk, encoding);
    return originalEnd(chunk, encoding, callback);
  };

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
      response_bytes: responseBytes,
      ...extra,
    });
    if (typeof onComplete === 'function') {
      onComplete({
        event,
        method: req.method,
        path: logPath,
        upstreamKind,
        statusCode: res.statusCode || upstreamStatus,
        upstreamStatus,
        upstreamHeaderMs,
        durationMs: roundedDurationMs(startedAt),
        responseBytes,
        ...extra,
      });
    }
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
    logCompletion(terminalEvent, terminalError ? { error: terminalError } : {});
  });

  res.on('close', () => {
    if (!res.writableEnded) {
      logCompletion(
        terminalEvent !== 'finish' ? terminalEvent : 'client_closed',
        terminalError ? { error: terminalError } : {},
      );
    }
  });

  if (upstreamKind === 'backend_execution_api' && tryProxyCachedDevApiRead(
    req,
    res,
    target,
    logCompletion,
    (errorCode) => {
      terminalEvent = 'upstream_error';
      terminalError = errorCode;
    },
  )) {
    return;
  }

  if (upstreamKind === 'next_dev' && tryProxySingleflightNextDocument(
    req,
    res,
    target,
    logCompletion,
    (errorCode) => {
      terminalEvent = 'upstream_error';
      terminalError = errorCode;
    },
  )) {
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
        terminalEvent = 'upstream_error';
        terminalError = error?.code || error?.message || 'upstream_response_error';
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
    terminalEvent = 'upstream_error';
    terminalError = error?.code || error?.message || 'unknown';
    if (!res.headersSent) {
      res.writeHead(502, { 'content-type': 'application/json', 'cache-control': 'no-store' });
    }
    if (!res.destroyed && !res.writableEnded) {
      res.end(JSON.stringify({ error: isDevApiProxyPath(req.url) ? 'backend_dev_proxy_unavailable' : 'next_dev_proxy_unavailable' }));
    }
  });

  req.pipe(upstream);
}

async function loadRemoteWorkbenchRunnerSnapshot() {
  const response = await fetch(buildInternalApiUrl('/api/v1/system-settings/health/queue/metrics'));
  if (!response.ok) {
    throw new Error(`queue_metrics_request_failed:${response.status}`);
  }
  return await response.json();
}

async function proxyUpgrade(
  req,
  socket,
  head,
  mobileWorkbenchGatewayConfig,
  deviceLinkIngressToken = '',
  resolveWorkspaceCapabilityPolicy = null,
  nextProxyTarget = null,
) {
  const requestResult = await isMobileWorkbenchGatewayRequestAllowedAsync(
    req.url,
    req.headers,
    mobileWorkbenchGatewayConfig,
    {
      deviceLinkIngressToken,
      requestMethod: req.method,
      resolveWorkspaceCapabilityPolicy,
    },
  );
  if (!requestResult.allowed) {
    const statusCode = Number(requestResult.status_code) === 403 ? 403 : 404;
    socket.end(`HTTP/1.1 ${statusCode} ${statusCode === 403 ? 'Forbidden' : 'Not Found'}\r\n\r\n`);
    return;
  }

  const target = isDevApiProxyPath(req.url)
    ? resolveDevApiProxyTarget(req.url)
    : resolveNextProxyTarget(req.url, nextProxyTarget);
  const upstream = net.connect(target.port, target.hostname, () => {
    const headers = copyProxyUpgradeHeaders(req.headers, target);
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

export function createFrontendProxyServer({
  nextRunningRef = { current: false },
  nextProxyTarget = null,
  mobileWorkbenchGatewayConfig = resolveMobileWorkbenchGatewayConfig(),
  deviceLinkIngressToken = '',
  remoteWorkbenchObservability = createRemoteWorkbenchObservability({
    loadRunnerSnapshot: loadRemoteWorkbenchRunnerSnapshot,
  }),
} = {}) {
  const resolveWorkspaceCapabilityPolicy = createMobileWorkbenchGatewayPolicyResolver({
    buildInternalApiUrl,
  });

  const server = http.createServer((req, res) => {
    void (async () => {
    if (isDeviceLinkHttpsHealthRequest(req.url, req.method)) {
      writeDeviceLinkHttpsHealth(res);
      return;
    }
    if (isMobileWorkbenchGatewayHealthRequest(req.url, req.method)) {
      writeMobileWorkbenchGatewayHealth(res, mobileWorkbenchGatewayConfig);
      return;
    }
    if (isMobileWorkbenchGatewaySummaryRequest(req.url, req.method)) {
      if (!isLoopbackControlPlaneRequest(req.headers)) {
        writeMobileWorkbenchGatewayRejection(
          res,
          { reason: 'mobile_workbench_gateway_path_not_allowed', status_code: 404 },
          req.url,
        );
        return;
      }
      await writeMobileWorkbenchGatewaySummary(res, remoteWorkbenchObservability, req.url);
      return;
    }
    if (isMobileWorkbenchGatewayAuditRequest(req.url, req.method)) {
      if (!isLoopbackControlPlaneRequest(req.headers)) {
        writeMobileWorkbenchGatewayRejection(
          res,
          { reason: 'mobile_workbench_gateway_path_not_allowed', status_code: 404 },
          req.url,
        );
        return;
      }
      await writeMobileWorkbenchGatewayAudit(res, remoteWorkbenchObservability, req.url);
      return;
    }
    if (isFrontendLivenessPath(req.url)) {
      writeFrontendLiveness(res, nextRunningRef.current);
      return;
    }
    if (isFrontendDocumentHeadReadinessRequest(req.method, req.url)) {
      writeFrontendDocumentHeadReadiness(res, nextRunningRef.current);
      return;
    }
    const requestId = ++requestSequence;
    const requestResult = await isMobileWorkbenchGatewayRequestAllowedAsync(
      req.url,
      req.headers,
      mobileWorkbenchGatewayConfig,
      {
        deviceLinkIngressToken,
        requestMethod: req.method,
        resolveWorkspaceCapabilityPolicy,
      },
    );
    const requestObservation = remoteWorkbenchObservability.createObservation({
      requestId,
      requestUrl: req.url,
      requestMethod: req.method,
      requestHeaders: req.headers,
      requestResult,
      mobileWorkbenchGatewayConfig,
    });
    if (!requestResult.allowed) {
      const rejection = writeMobileWorkbenchGatewayRejection(res, requestResult, req.url);
      void remoteWorkbenchObservability.recordDeniedRequest(requestObservation, {
        requestResult,
        statusCode: rejection.statusCode,
        responseBytes: rejection.bodyBytes,
      });
      return;
    }

    proxyHttpRequest(req, res, {
      requestId,
      nextProxyTarget,
      onComplete: (event) => {
        void remoteWorkbenchObservability.recordCompletedRequest(requestObservation, event);
      },
    });
    })().catch((error) => {
      if (!res.headersSent) {
        res.writeHead(500, { 'content-type': 'application/json', 'cache-control': 'no-store' });
      }
      if (!res.writableEnded) {
        res.end(JSON.stringify({
          error: 'frontend_proxy_request_failed',
          detail: error?.message || 'unknown_error',
        }));
      }
    });
  });

  server.on('upgrade', (req, socket, head) => {
    void proxyUpgrade(
      req,
      socket,
      head,
      mobileWorkbenchGatewayConfig,
      deviceLinkIngressToken,
      resolveWorkspaceCapabilityPolicy,
      nextProxyTarget,
    ).catch(() => {
      socket.destroy();
    });
  });
  server.on('clientError', (_error, socket) => {
    socket.end('HTTP/1.1 400 Bad Request\r\n\r\n');
  });

  return server;
}

export function start() {
  const nextRunningRef = { current: false };
  const deviceLinkIngressToken = createDeviceLinkIngressToken();
  let nextProcess = null;
  let restartTimer = null;
  let prewarmTimer = null;
  let deviceLinkHttpsServer = null;
  let restartCount = 0;
  let shuttingDown = false;
  const server = createFrontendProxyServer({ nextRunningRef, deviceLinkIngressToken });

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
    deviceLinkHttpsServer = startDeviceLinkHttpsProxy({
      targetHost: '127.0.0.1',
      targetPort: PUBLIC_PORT,
      ingressToken: deviceLinkIngressToken,
    });
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
    deviceLinkHttpsServer?.close();
    deviceLinkHttpsServer = null;
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
