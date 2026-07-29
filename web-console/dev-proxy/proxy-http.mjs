import http from 'node:http';
import { performance } from 'node:perf_hooks';
import { resolveApiRoutePlane } from './api-route-plane.mjs';
import {
  buildInternalApiUrl,
  isDevApiProxyPath,
  resolveDevApiProxyTarget,
} from './api-target.mjs';
import {
  tryProxyCachedDevApiRead,
} from './dev-api-read-cache.mjs';
import {
  tryProxySingleflightNextDocument,
} from './frontend-document-stream.mjs';
import {
  copyProxyRequestHeaders,
  copyProxyResponseHeaders,
} from './proxy-headers.mjs';

const NEXT_HOST = process.env.NEXT_DEV_HOST || '127.0.0.1';
const NEXT_PORT = Number.parseInt(process.env.NEXT_DEV_PORT || '3002', 10);
const NEXT_DEV_TURBO_ENABLED = process.env.NEXT_DEV_TURBO === '1';
const PROXY_LOG_MODE = process.env.FRONTEND_PROXY_LOG_MODE || 'slow';
const PROXY_SLOW_LOG_THRESHOLD_MS = Number.parseInt(
  process.env.FRONTEND_PROXY_SLOW_LOG_THRESHOLD_MS || '1000',
  10,
);
let requestSequence = 0;

export function normalizeProxyLogPath(requestUrl = '/') {
  try {
    return new URL(requestUrl, 'http://localhost').pathname;
  } catch {
    const value = String(requestUrl || '/');
    return value.split('?')[0] || '/';
  }
}

export function classifyProxyUpstream(requestUrl = '/', method = 'GET') {
  if (isDevApiProxyPath(requestUrl)) {
    const routePlane = resolveApiRoutePlane(requestUrl, method);
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

export function resolveNextProxyTarget(requestUrl = '/', nextProxyTarget = null) {
  return {
    hostname: nextProxyTarget?.hostname || NEXT_HOST,
    port: nextProxyTarget?.port || NEXT_PORT,
    protocol: 'http:',
    path: requestUrl,
  };
}

export function proxyHttpRequest(
  req,
  res,
  {
    requestId = ++requestSequence,
    onComplete = null,
    nextProxyTarget = null,
    stripRemoteIdentityHeaders = false,
    trustedRemoteIdentity = null,
  } = {},
) {
  const startedAt = performance.now();
  const upstreamKind = classifyProxyUpstream(req.url, req.method);
  const logPath = normalizeProxyLogPath(req.url);
  let upstreamStatus = null;
  let upstreamHeaderMs = null;
  let completionLogged = false;
  let responseBytes = 0;
  let terminalEvent = 'finish';
  let terminalError = null;
  const target = upstreamKind.startsWith('backend_') || upstreamKind === 'media_proxy'
    ? resolveDevApiProxyTarget(req.url, req.method)
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

  if (!stripRemoteIdentityHeaders && upstreamKind === 'backend_execution_api' && tryProxyCachedDevApiRead(
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

  if (!stripRemoteIdentityHeaders && upstreamKind === 'next_dev' && tryProxySingleflightNextDocument(
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
      headers: copyProxyRequestHeaders(req.headers, target, {
        stripRemoteIdentityHeaders,
        trustedRemoteIdentity,
      }),
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
      res.end(JSON.stringify({
        error: isDevApiProxyPath(req.url) ? 'backend_dev_proxy_unavailable' : 'next_dev_proxy_unavailable',
      }));
    }
  });

  req.pipe(upstream);
}

export async function loadRemoteWorkbenchRunnerSnapshot() {
  const response = await fetch(buildInternalApiUrl('/api/v1/system-settings/health/queue/metrics'));
  if (!response.ok) {
    throw new Error(`queue_metrics_request_failed:${response.status}`);
  }
  return await response.json();
}
