import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { resolveApiRoutePlane } from './api-route-plane.mjs';

const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));
const WEB_CONSOLE_DIR = path.resolve(MODULE_DIR, '..');
const SERVICE_ENDPOINT_SEED_PATHS = [
  process.env.MINDSCAPE_SERVICE_ENDPOINT_SEED,
  '/app/config/service-endpoints.seed.json',
  path.resolve(WEB_CONSOLE_DIR, '../config/service-endpoints.seed.json'),
].filter(Boolean);
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

export function buildInternalApiUrl(requestPath = '/') {
  const target = resolveDevApiProxyTarget(requestPath);
  const port = target.port ? `:${target.port}` : '';
  return `${target.protocol}//${target.hostname}${port}${target.path}`;
}
