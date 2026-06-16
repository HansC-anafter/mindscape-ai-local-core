import net from 'node:net';
import {
  isMobileWorkbenchGatewayRequestAllowedAsync,
} from './mobile-workbench-gateway.mjs';
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

export async function proxyUpgrade(
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
