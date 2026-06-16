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

export function copyProxyRequestHeaders(headers, target) {
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
