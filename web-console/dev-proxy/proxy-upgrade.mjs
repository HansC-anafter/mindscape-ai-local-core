import net from 'node:net';

import {
  isDevApiProxyPath,
  resolveDevApiProxyTarget,
} from './api-target.mjs';
import {
  copyProxyUpgradeHeaders,
} from './proxy-headers.mjs';
import {
  resolveNextProxyTarget,
} from './proxy-http.mjs';

function safeHeaderValue(value, fallback) {
  const normalized = String(value || fallback).replace(/[^a-zA-Z0-9_.-]/g, '_');
  return normalized.slice(0, 128) || fallback;
}

export async function proxyUpgrade(
  req,
  socket,
  head,
  {
    authorizeRequest = async () => ({ allowed: true }),
    nextProxyTarget = null,
    stripRemoteIdentityHeaders = false,
  } = {},
) {
  const requestResult = await authorizeRequest(req);
  if (!requestResult.allowed) {
    const statusCode = Number(requestResult.status_code) === 403 ? 403 : 404;
    const reason = safeHeaderValue(
      requestResult.reason_code,
      'mobile_workbench_gateway_access_denied',
    );
    const stage = safeHeaderValue(requestResult.verification_stage, 'identity_rejected');
    socket.end(
      `HTTP/1.1 ${statusCode} ${statusCode === 403 ? 'Forbidden' : 'Not Found'}\r\n`
      + `X-Mindscape-Remote-Auth-Stage: ${stage}\r\n`
      + `X-Mindscape-Remote-Auth-Reason: ${reason}\r\n\r\n`,
    );
    return;
  }

  const target = isDevApiProxyPath(req.url)
    ? resolveDevApiProxyTarget(req.url)
    : resolveNextProxyTarget(req.url, nextProxyTarget);
  const upstream = net.connect(target.port, target.hostname, () => {
    const headers = copyProxyUpgradeHeaders(req.headers, target, {
      stripRemoteIdentityHeaders,
    });
    upstream.write(
      `${req.method} ${target.path} HTTP/${req.httpVersion}\r\n`
      + Object.entries(headers)
        .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`)
        .join('\r\n')
      + '\r\n\r\n',
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
