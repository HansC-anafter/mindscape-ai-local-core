import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { performance } from 'node:perf_hooks';
import { fileURLToPath } from 'node:url';

const NEXT_HOST = process.env.NEXT_DEV_HOST || '127.0.0.1';
const NEXT_PORT = Number.parseInt(process.env.NEXT_DEV_PORT || '3001', 10);
const PREWARM_WORKSPACE_ID = process.env.FRONTEND_PREWARM_WORKSPACE_ID || '__prewarm__';
const PREWARM_TIMEOUT_MS = Number.parseInt(process.env.FRONTEND_PREWARM_TIMEOUT_MS || '360000', 10);
const CAPABILITY_PREWARM_ENABLED = process.env.FRONTEND_CAPABILITY_PREWARM_ENABLED === '1';
const CAPABILITY_HOST_PREWARM_ENABLED = process.env.FRONTEND_CAPABILITY_HOST_PREWARM_ENABLED === '1';
const CORE_PREWARM_PATHS = [];
const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));
const SERVICE_ENDPOINT_SEED_PATHS = [
  process.env.MINDSCAPE_SERVICE_ENDPOINT_SEED,
  '/app/config/service-endpoints.seed.json',
  path.resolve(MODULE_DIR, '../../config/service-endpoints.seed.json'),
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

function roundedDurationMs(startedAt) {
  return Math.round((performance.now() - startedAt) * 100) / 100;
}

function normalizeBaseUrl(value, fallback) {
  const resolved = String(value || '').trim() || fallback;
  return resolved.replace(/\/+$/, '');
}

function isCapabilityPrewarmPath(pathValue) {
  return String(pathValue || '').includes('/capability-ui-hosts/') ||
    String(pathValue || '').includes('/capabilities/');
}

function applyWorkspaceId(pathValue, workspaceId) {
  return String(pathValue || '').trim().replaceAll('{workspaceId}', encodeURIComponent(workspaceId));
}

function uniquePaths(paths) {
  const seen = new Set();
  const nextPaths = [];
  for (const pathValue of paths) {
    const normalized = String(pathValue || '').trim();
    if (!normalized || seen.has(normalized)) {
      continue;
    }
    seen.add(normalized);
    nextPaths.push(normalized);
  }
  return nextPaths;
}

export function resolveCorePrewarmPaths(
  rawPaths = process.env.FRONTEND_PREWARM_PATHS,
  workspaceId = PREWARM_WORKSPACE_ID,
) {
  const sourcePaths = String(rawPaths || '').trim()
    ? String(rawPaths).split(/[\n,]/)
    : CORE_PREWARM_PATHS;
  return uniquePaths(
    sourcePaths
      .map((pathValue) => applyWorkspaceId(pathValue, workspaceId))
      .filter((pathValue) => !isCapabilityPrewarmPath(pathValue)),
  );
}

function normalizeSurfacePath(surface) {
  if (!surface || typeof surface !== 'object') {
    return '';
  }
  const rawPath = String(surface.path || '').trim();
  if (!rawPath) {
    return '';
  }
  return rawPath.startsWith('/') ? rawPath.replace(/^\/+/, '') : rawPath;
}

export function buildCapabilityPrewarmPaths(
  capabilities,
  workspaceId = PREWARM_WORKSPACE_ID,
  capabilityPrewarmEnabled = CAPABILITY_PREWARM_ENABLED,
  capabilityHostPrewarmEnabled = CAPABILITY_HOST_PREWARM_ENABLED,
) {
  if (!capabilityPrewarmEnabled || !capabilityHostPrewarmEnabled) {
    return [];
  }
  if (!Array.isArray(capabilities)) {
    return [];
  }
  const encodedWorkspaceId = encodeURIComponent(workspaceId);
  const paths = [];
  for (const capability of capabilities) {
    if (!capability || typeof capability !== 'object') {
      continue;
    }
    const prewarm = capability.ui_prewarm;
    if (!prewarm || prewarm.enabled !== true) {
      continue;
    }
    const capabilityCode = String(capability.code || capability.id || '').trim();
    if (!capabilityCode) {
      continue;
    }
    const encodedCapabilityCode = encodeURIComponent(capabilityCode);
    const surfaces = Array.isArray(prewarm.surfaces) && prewarm.surfaces.length > 0
      ? prewarm.surfaces
      : [{ path: '' }];
    for (const surface of surfaces) {
      const surfacePath = normalizeSurfacePath(surface);
      const suffix = surfacePath ? `/${surfacePath}` : '';
      paths.push(`/workspaces/${encodedWorkspaceId}/capability-ui-hosts/${encodedCapabilityCode}${suffix}`);
    }
  }
  return uniquePaths(paths);
}

function requestJson(url, timeoutMs = PREWARM_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const startedAt = performance.now();
    const request = http.request(
      {
        hostname: parsed.hostname,
        port: Number.parseInt(parsed.port || (parsed.protocol === 'https:' ? '443' : '80'), 10),
        method: 'GET',
        path: `${parsed.pathname}${parsed.search}`,
        headers: {
          host: parsed.port ? `${parsed.hostname}:${parsed.port}` : parsed.hostname,
          'x-mindscape-frontend-prewarm-metadata': '1',
        },
      },
      (response) => {
        const chunks = [];
        response.on('data', (chunk) => chunks.push(chunk));
        response.on('end', () => {
          if ((response.statusCode || 500) < 200 || (response.statusCode || 500) >= 300) {
            reject(new Error(`metadata_request_failed:${response.statusCode || 0}`));
            return;
          }
          try {
            resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')));
          } catch (error) {
            reject(error);
          }
        });
      },
    );
    request.setTimeout(timeoutMs, () => {
      request.destroy(new Error(`metadata_request_timeout:${roundedDurationMs(startedAt)}`));
    });
    request.on('error', reject);
    request.end();
  });
}

export async function fetchInstalledCapabilityMetadata(
  backendBaseUrl = normalizeBaseUrl(
    process.env.WEB_CONSOLE_BACKEND_URL ||
      process.env.BACKEND_URL ||
      process.env.NEXT_PUBLIC_BACKEND_URL,
    resolveSeedEndpointUrl('local_core.control_api', 'server_internal') ||
      resolveSeedEndpointUrl('local_core.control_api', 'container_internal'),
  ),
) {
  const fallbackBaseUrl =
    resolveSeedEndpointUrl('local_core.control_api', 'server_internal') ||
    resolveSeedEndpointUrl('local_core.control_api', 'container_internal');
  return requestJson(`${normalizeBaseUrl(backendBaseUrl, fallbackBaseUrl)}/api/v1/capability-packs/installed-capabilities`);
}

export async function resolveFrontendPrewarmPaths(
  rawPaths = process.env.FRONTEND_PREWARM_PATHS,
  workspaceId = PREWARM_WORKSPACE_ID,
  options = {},
) {
  const corePaths = resolveCorePrewarmPaths(rawPaths, workspaceId);
  const capabilities = Array.isArray(options.installedCapabilities)
    ? options.installedCapabilities
    : await (options.fetchInstalledCapabilities || fetchInstalledCapabilityMetadata)();
  return uniquePaths([
    ...corePaths,
    ...buildCapabilityPrewarmPaths(
      capabilities,
      workspaceId,
      options.capabilityPrewarmEnabled ?? CAPABILITY_PREWARM_ENABLED,
      options.capabilityHostPrewarmEnabled ?? CAPABILITY_HOST_PREWARM_ENABLED,
    ),
  ]);
}

export function prewarmNextDevPath(pathValue) {
  return new Promise((resolve) => {
    const startedAt = performance.now();
    let settled = false;
    const finish = (event, extra = {}) => {
      if (settled) {
        return;
      }
      settled = true;
      console.log(`[frontend-proxy] ${event} ${JSON.stringify({
        path: pathValue,
        duration_ms: roundedDurationMs(startedAt),
        ...extra,
      })}`);
      resolve();
    };
    const request = http.request(
      {
        hostname: NEXT_HOST,
        port: NEXT_PORT,
        method: 'GET',
        path: pathValue,
        headers: {
          host: `${NEXT_HOST}:${NEXT_PORT}`,
          'x-mindscape-frontend-prewarm': '1',
        },
      },
      (response) => {
        finish('prewarm', {
          status: response.statusCode || null,
        });
        response.resume();
        response.destroy();
      },
    );

    request.setTimeout(PREWARM_TIMEOUT_MS, () => {
      finish('prewarm_triggered', { reason: 'timeout' });
      request.destroy(new Error('prewarm_trigger_timeout'));
    });
    request.on('error', (error) => {
      if (settled) {
        return;
      }
      console.error(`[frontend-proxy] prewarm_failed ${JSON.stringify({
        path: pathValue,
        duration_ms: roundedDurationMs(startedAt),
        error: error?.code || error?.message || 'unknown',
      })}`);
      resolve();
    });
    request.end();
  });
}

export function waitForNextDevReady(timeoutMs = PREWARM_TIMEOUT_MS) {
  return new Promise((resolve) => {
    const startedAt = performance.now();
    let settled = false;

    const finish = (ready) => {
      if (settled) {
        return;
      }
      settled = true;
      resolve(ready);
    };

    const probe = () => {
      if (performance.now() - startedAt >= timeoutMs) {
        console.error(`[frontend-proxy] prewarm_wait_failed ${JSON.stringify({
          duration_ms: roundedDurationMs(startedAt),
          reason: 'timeout',
        })}`);
        finish(false);
        return;
      }

      const request = http.request(
        {
          hostname: NEXT_HOST,
          port: NEXT_PORT,
          method: 'GET',
          path: '/healthz',
          headers: {
            host: `${NEXT_HOST}:${NEXT_PORT}`,
            'x-mindscape-frontend-prewarm-probe': '1',
          },
        },
        (response) => {
          response.resume();
          finish(true);
        },
      );

      request.setTimeout(1000, () => {
        request.destroy(new Error('prewarm_probe_timeout'));
      });
      request.on('error', () => {
        setTimeout(probe, 500);
      });
      request.end();
    };

    probe();
  });
}

export async function prewarmNextDevRoutes(pathsPromise = resolveFrontendPrewarmPaths(), options = {}) {
  const shouldContinue = typeof options.shouldContinue === 'function'
    ? options.shouldContinue
    : () => true;
  const stopReason = String(options.stopReason || 'foreground_activity');
  let paths = [];
  try {
    paths = await pathsPromise;
  } catch (error) {
    console.error(`[frontend-proxy] prewarm_metadata_failed ${JSON.stringify({
      error: error?.message || 'unknown',
    })}`);
    paths = resolveCorePrewarmPaths('', PREWARM_WORKSPACE_ID);
  }
  if (!paths.length) {
    console.log('[frontend-proxy] prewarm_skipped {"reason":"no_paths"}');
    return;
  }
  if (!shouldContinue()) {
    console.log(`[frontend-proxy] prewarm_skipped ${JSON.stringify({ reason: stopReason })}`);
    return;
  }
  console.log(`[frontend-proxy] prewarm_start ${JSON.stringify({ paths })}`);
  const ready = await waitForNextDevReady();
  if (!ready) {
    console.log('[frontend-proxy] prewarm_skipped {"reason":"next_dev_unavailable"}');
    return;
  }
  for (const [index, pathValue] of paths.entries()) {
    if (!shouldContinue()) {
      console.log(`[frontend-proxy] prewarm_stopped ${JSON.stringify({
        reason: stopReason,
        completed: index,
        remaining: paths.length - index,
      })}`);
      return;
    }
    await prewarmNextDevPath(pathValue);
  }
  console.log(`[frontend-proxy] prewarm_done ${JSON.stringify({ count: paths.length })}`);
}
