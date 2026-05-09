import http from 'node:http';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { performance } from 'node:perf_hooks';

const PUBLIC_HOST = process.env.FRONTEND_PROXY_HOST || '0.0.0.0';
const PUBLIC_PORT = Number.parseInt(process.env.PORT || '3000', 10);
const NEXT_HOST = process.env.NEXT_DEV_HOST || '127.0.0.1';
const NEXT_PORT = Number.parseInt(process.env.NEXT_DEV_PORT || '3001', 10);
const DEFAULT_BACKEND_URL = 'http://backend:8200';
const DEFAULT_MEDIA_PROXY_URL = 'http://media-proxy:8000';
const PROXY_LOG_MODE = process.env.FRONTEND_PROXY_LOG_MODE || 'slow';
const PROXY_SLOW_LOG_THRESHOLD_MS = Number.parseInt(
  process.env.FRONTEND_PROXY_SLOW_LOG_THRESHOLD_MS || '1000',
  10,
);
const PREWARM_WORKSPACE_ID = process.env.FRONTEND_PREWARM_WORKSPACE_ID || '__prewarm__';
const PREWARM_ENABLED = process.env.FRONTEND_PREWARM_ENABLED === '1';
const PREWARM_DELAY_MS = Number.parseInt(process.env.FRONTEND_PREWARM_DELAY_MS || '15000', 10);
const PREWARM_TIMEOUT_MS = Number.parseInt(process.env.FRONTEND_PREWARM_TIMEOUT_MS || '180000', 10);
const NEXT_DEV_TURBO_ENABLED = process.env.NEXT_DEV_TURBO === '1';
const DEFAULT_PREWARM_PATHS = [];
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
let requestSequence = 0;

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
  const baseUrl = parsed.pathname.startsWith('/api/v1/media/')
    ? normalizeBaseUrl(process.env.MEDIA_PROXY_URL, DEFAULT_MEDIA_PROXY_URL)
    : normalizeBaseUrl(
        process.env.WEB_CONSOLE_BACKEND_URL ||
          process.env.BACKEND_URL ||
          process.env.NEXT_PUBLIC_BACKEND_URL,
        DEFAULT_BACKEND_URL,
      );
  const upstream = new URL(baseUrl);
  return {
    hostname: upstream.hostname,
    port: Number.parseInt(upstream.port || (upstream.protocol === 'https:' ? '443' : '80'), 10),
    protocol: upstream.protocol,
    path: `${parsed.pathname}${parsed.search}`,
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

function copyProxyResponseHeaders(headers) {
  const nextHeaders = {};
  for (const [key, value] of Object.entries(headers || {})) {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
      nextHeaders[key] = value;
    }
  }
  nextHeaders['cache-control'] = 'no-store';
  return nextHeaders;
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
    return new URL(requestUrl, 'http://localhost').pathname.startsWith('/api/v1/media/')
      ? 'media_proxy'
      : 'backend_api';
  }
  return 'next_dev';
}

function roundedDurationMs(startedAt) {
  return Math.round((performance.now() - startedAt) * 100) / 100;
}

export function resolveFrontendPrewarmPaths(
  rawPaths = process.env.FRONTEND_PREWARM_PATHS,
  workspaceId = PREWARM_WORKSPACE_ID,
) {
  const sourcePaths = String(rawPaths || '').trim()
    ? String(rawPaths).split(/[\n,]/)
    : DEFAULT_PREWARM_PATHS;
  return sourcePaths
    .map((pathValue) => String(pathValue || '').trim())
    .filter(Boolean)
    .map((pathValue) => pathValue.replaceAll('{workspaceId}', encodeURIComponent(workspaceId)));
}

export function resolveNextDevArgs(
  host = NEXT_HOST,
  port = NEXT_PORT,
  turboEnabled = NEXT_DEV_TURBO_ENABLED,
) {
  return [
    'run',
    'dev',
    '--',
    ...(turboEnabled ? ['--turbo'] : []),
    '-H',
    host,
    '-p',
    String(port),
  ];
}

function prewarmNextDevPath(pathValue) {
  return new Promise((resolve) => {
    const startedAt = performance.now();
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
        response.resume();
        response.on('end', () => {
          console.log(`[frontend-proxy] prewarm ${JSON.stringify({
            path: pathValue,
            status: response.statusCode || null,
            duration_ms: roundedDurationMs(startedAt),
          })}`);
          resolve();
        });
      },
    );

    request.setTimeout(PREWARM_TIMEOUT_MS, () => {
      request.destroy(new Error('prewarm_timeout'));
    });
    request.on('error', (error) => {
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

async function prewarmNextDevRoutes(paths = resolveFrontendPrewarmPaths()) {
  for (const pathValue of paths) {
    await prewarmNextDevPath(pathValue);
  }
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
  console.log(`[frontend-proxy] request ${JSON.stringify(event)}`);
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
  const target = upstreamKind === 'backend_api' || upstreamKind === 'media_proxy'
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

  res.on('finish', () => {
    logCompletion('finish');
  });

  res.on('close', () => {
    if (!res.writableEnded) {
      logCompletion('client_closed');
    }
  });

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
      res.writeHead(upstreamRes.statusCode || 502, copyProxyResponseHeaders(upstreamRes.headers));
      upstreamRes.pipe(res);
    },
  );

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
    res.end(JSON.stringify({ error: isDevApiProxyPath(req.url) ? 'backend_dev_proxy_unavailable' : 'next_dev_proxy_unavailable' }));
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
