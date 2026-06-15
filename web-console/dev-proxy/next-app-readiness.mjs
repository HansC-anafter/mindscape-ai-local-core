import { performance } from 'node:perf_hooks';
import { fileURLToPath } from 'node:url';

export const DEFAULT_NEXT_APP_READINESS_TIMEOUT_MS = 12000;
export const DEFAULT_NEXT_APP_READINESS_PATHS = [
  '/healthz',
  '/',
];

function normalizeProbePath(value) {
  const normalized = String(value || '').trim();
  if (!normalized) {
    return null;
  }
  if (/^https?:\/\//i.test(normalized)) {
    const parsed = new URL(normalized);
    return `${parsed.pathname}${parsed.search}`;
  }
  return normalized.startsWith('/') ? normalized : `/${normalized}`;
}

export function parseNextAppReadinessPaths(
  value,
  fallbackPaths = DEFAULT_NEXT_APP_READINESS_PATHS,
) {
  const rawPaths = Array.isArray(value)
    ? value
    : String(value || '').split(',');
  const paths = rawPaths
    .map(normalizeProbePath)
    .filter(Boolean);
  if (paths.length > 0) {
    return Array.from(new Set(paths));
  }
  return Array.from(new Set(fallbackPaths.map(normalizeProbePath).filter(Boolean)));
}

export function resolveNextAppReadinessConfig(env = process.env) {
  const host = String(env.NEXT_DEV_HOST || '127.0.0.1').trim() || '127.0.0.1';
  const parsedPort = Number.parseInt(String(env.NEXT_DEV_PORT || '3001'), 10);
  const parsedTimeoutMs = Number.parseInt(
    String(env.FRONTEND_APP_READINESS_TIMEOUT_MS || DEFAULT_NEXT_APP_READINESS_TIMEOUT_MS),
    10,
  );
  const port = Number.isInteger(parsedPort) && parsedPort > 0 ? parsedPort : 3001;
  const timeoutMs = Number.isInteger(parsedTimeoutMs) && parsedTimeoutMs > 0
    ? parsedTimeoutMs
    : DEFAULT_NEXT_APP_READINESS_TIMEOUT_MS;

  return {
    host,
    paths: parseNextAppReadinessPaths(env.FRONTEND_APP_READINESS_PATHS),
    port,
    timeoutMs,
  };
}

function buildProbeUrl(config, probePath) {
  return `http://${config.host}:${config.port}${probePath}`;
}

export async function probeNextAppRoute(
  config,
  probePath,
  {
    fetchImpl = globalThis.fetch,
  } = {},
) {
  const path = normalizeProbePath(probePath) || '/';
  const url = buildProbeUrl(config, path);
  const startedAt = performance.now();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.timeoutMs);

  try {
    const response = await fetchImpl(url, {
      cache: 'no-store',
      signal: controller.signal,
    });
    const body = await response.arrayBuffer();
    const totalMs = Math.round((performance.now() - startedAt) * 100) / 100;
    return {
      path,
      status: response.status,
      ok: response.status >= 200 && response.status < 500,
      total_ms: totalMs,
      bytes: body.byteLength,
    };
  } catch (error) {
    const totalMs = Math.round((performance.now() - startedAt) * 100) / 100;
    return {
      path,
      status: null,
      ok: false,
      total_ms: totalMs,
      bytes: 0,
      error: error?.name || 'Error',
      message: error?.message || 'unknown_error',
    };
  } finally {
    clearTimeout(timeout);
  }
}

export async function probeNextAppReadiness(
  config = resolveNextAppReadinessConfig(),
  options = {},
) {
  const results = [];
  for (const probePath of config.paths) {
    results.push(await probeNextAppRoute(config, probePath, options));
  }
  return {
    ok: results.every((result) => result.ok),
    host: config.host,
    port: config.port,
    timeout_ms: config.timeoutMs,
    results,
  };
}

export function formatNextAppReadinessResult(result) {
  return JSON.stringify(result);
}

function isCliEntrypoint(moduleUrl) {
  return process.argv[1] && fileURLToPath(moduleUrl) === process.argv[1];
}

if (isCliEntrypoint(import.meta.url)) {
  const result = await probeNextAppReadiness();
  console.log(formatNextAppReadinessResult(result));
  process.exit(result.ok ? 0 : 1);
}
