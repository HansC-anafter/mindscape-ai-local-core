import fs from 'node:fs';
import http from 'node:http';
import https from 'node:https';
import net from 'node:net';

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

export function isAllowedDeviceLinkHttpsPath(requestUrl = '/') {
  try {
    const parsed = new URL(requestUrl, 'https://localhost');
    return (
      parsed.pathname === '/favicon.ico' ||
      parsed.pathname === '/device-link/health' ||
      parsed.pathname === '/device-link/__test__' ||
      parsed.pathname.startsWith('/device-link/') ||
      parsed.pathname.startsWith('/_next/') ||
      parsed.pathname.startsWith('/api/')
    );
  } catch {
    return false;
  }
}

export function isDeviceLinkHttpsReadinessPath(requestUrl = '/') {
  try {
    const parsed = new URL(requestUrl, 'https://localhost');
    return (
      parsed.pathname === '/device-link/health' ||
      parsed.pathname === '/device-link/__test__'
    );
  } catch {
    return false;
  }
}

export function resolveDeviceLinkHttpsConfig(env = process.env) {
  const enabled = String(env.DEVICE_LINK_HTTPS_ENABLED || '').trim() === '1';
  const publicOrigin = String(env.DEVICE_LINK_PUBLIC_ORIGIN || '').trim().replace(/\/+$/, '');
  const certFile = String(env.DEVICE_LINK_HTTPS_CERT_FILE || '').trim();
  const keyFile = String(env.DEVICE_LINK_HTTPS_KEY_FILE || '').trim();
  const host = String(env.DEVICE_LINK_HTTPS_HOST || '0.0.0.0').trim() || '0.0.0.0';
  const port = Number.parseInt(String(env.DEVICE_LINK_HTTPS_PORT || '8343'), 10);
  const errors = [];

  if (!enabled) {
    return {
      enabled: false,
      reason: 'disabled',
      errors,
      host,
      port,
      publicOrigin,
      certFile,
      keyFile,
    };
  }
  if (!publicOrigin) {
    errors.push('DEVICE_LINK_PUBLIC_ORIGIN_required');
  } else if (!publicOrigin.startsWith('https://')) {
    errors.push('DEVICE_LINK_PUBLIC_ORIGIN_must_use_https');
  }
  if (!certFile) {
    errors.push('DEVICE_LINK_HTTPS_CERT_FILE_required');
  }
  if (!keyFile) {
    errors.push('DEVICE_LINK_HTTPS_KEY_FILE_required');
  }
  if (!Number.isInteger(port) || port <= 0 || port > 65535) {
    errors.push('DEVICE_LINK_HTTPS_PORT_invalid');
  }

  return {
    enabled: errors.length === 0,
    reason: errors.length ? 'invalid_config' : 'enabled',
    errors,
    host,
    port,
    publicOrigin,
    certFile,
    keyFile,
  };
}

export function writeDeviceLinkHttpsReadiness(res, config) {
  const body = JSON.stringify({
    status: 'ok',
    service: 'device-link-https',
    public_origin: config.publicOrigin,
  });
  res.writeHead(200, {
    'content-type': 'application/json',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(body),
  });
  res.end(body);
}

function copyProxyRequestHeaders(headers, target) {
  const nextHeaders = {};
  for (const [key, value] of Object.entries(headers || {})) {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase()) && key.toLowerCase() !== 'host') {
      nextHeaders[key] = value;
    }
  }
  nextHeaders.host = `${target.hostname}:${target.port}`;
  nextHeaders['x-forwarded-proto'] = 'https';
  nextHeaders['x-mindscape-device-link-https'] = '1';
  return nextHeaders;
}

function copyProxyUpgradeHeaders(headers, target) {
  const nextHeaders = copyProxyRequestHeaders(headers, target);
  const upgradeHeader = headers?.upgrade;
  nextHeaders.connection = 'Upgrade';
  nextHeaders.upgrade = Array.isArray(upgradeHeader)
    ? upgradeHeader[0] || 'websocket'
    : upgradeHeader || 'websocket';
  return nextHeaders;
}

function writeRejectedPath(res) {
  const body = JSON.stringify({ error: 'device_link_https_path_not_allowed' });
  res.writeHead(404, {
    'content-type': 'application/json',
    'cache-control': 'no-store',
    'content-length': Buffer.byteLength(body),
  });
  res.end(body);
}

function proxyHttpsRequest(req, res, target, config) {
  if (!isAllowedDeviceLinkHttpsPath(req.url)) {
    writeRejectedPath(res);
    return;
  }
  if (isDeviceLinkHttpsReadinessPath(req.url) && (req.method === 'GET' || req.method === 'HEAD')) {
    writeDeviceLinkHttpsReadiness(res, config);
    return;
  }

  const upstream = http.request(
    {
      hostname: target.hostname,
      port: target.port,
      method: req.method,
      path: req.url,
      headers: copyProxyRequestHeaders(req.headers, target),
    },
    (upstreamRes) => {
      const responseHeaders = {};
      for (const [key, value] of Object.entries(upstreamRes.headers || {})) {
        if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
          responseHeaders[key] = value;
        }
      }
      responseHeaders['cache-control'] = responseHeaders['cache-control'] || 'no-store';
      res.writeHead(upstreamRes.statusCode || 502, responseHeaders);
      upstreamRes.pipe(res);
    },
  );
  upstream.on('error', () => {
    if (!res.headersSent) {
      res.writeHead(502, { 'content-type': 'application/json', 'cache-control': 'no-store' });
    }
    if (!res.destroyed && !res.writableEnded) {
      res.end(JSON.stringify({ error: 'device_link_https_proxy_unavailable' }));
    }
  });
  req.pipe(upstream);
}

function proxyHttpsUpgrade(req, socket, head, target) {
  if (!isAllowedDeviceLinkHttpsPath(req.url)) {
    socket.end('HTTP/1.1 404 Not Found\r\n\r\n');
    return;
  }
  const upstream = net.connect(target.port, target.hostname, () => {
    const headers = copyProxyUpgradeHeaders(req.headers, target);
    upstream.write(
      `${req.method} ${req.url} HTTP/${req.httpVersion}\r\n` +
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

export function startDeviceLinkHttpsProxy({
  targetHost = '127.0.0.1',
  targetPort,
  env = process.env,
} = {}) {
  const config = resolveDeviceLinkHttpsConfig(env);
  if (config.reason === 'disabled') {
    return null;
  }
  if (!config.enabled) {
    throw new Error(`device_link_https_invalid_config:${config.errors.join(',')}`);
  }
  const target = {
    hostname: targetHost,
    port: Number(targetPort),
  };
  const server = https.createServer(
    {
      cert: fs.readFileSync(config.certFile),
      key: fs.readFileSync(config.keyFile),
    },
    (req, res) => proxyHttpsRequest(req, res, target, config),
  );
  server.on('upgrade', (req, socket, head) => {
    proxyHttpsUpgrade(req, socket, head, target);
  });
  server.on('clientError', (_error, socket) => {
    socket.end('HTTP/1.1 400 Bad Request\r\n\r\n');
  });
  server.listen(config.port, config.host, () => {
    console.log(
      `[device-link-https] listening on ${config.host}:${config.port}, public_origin=${config.publicOrigin}`,
    );
  });
  return server;
}
