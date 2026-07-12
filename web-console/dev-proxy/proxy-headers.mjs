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

const REMOTE_IDENTITY_HEADERS = new Set([
  'authorization',
  'cf-access-jwt-assertion',
  'cf-authorization',
  'cf_authorization',
  'remote-user',
  'x-forwarded-email',
  'x-forwarded-user',
  'x-mindscape-device-link-ingress-token',
  'x-mindscape-user-email',
  'x-mindscape-user-id',
  'x-user-email',
  'x-user-id',
]);
const REMOTE_INGRESS_HEADER = 'x-mindscape-remote-ingress';

function isRemoteIdentityHeader(headerName) {
  const normalized = String(headerName || '').toLowerCase();
  return REMOTE_IDENTITY_HEADERS.has(normalized)
    || normalized.startsWith('cf-access-')
    || normalized.startsWith('x-auth-request-')
    || normalized.startsWith('x-mindscape-identity-');
}

function stripCloudflareAccessCookie(value) {
  const values = Array.isArray(value) ? value : [value];
  const filtered = values
    .flatMap((item) => String(item || '').split(';'))
    .map((item) => item.trim())
    .filter((item) => item && !/^CF_Authorization=/i.test(item));
  return filtered.join('; ');
}

export function copyProxyRequestHeaders(
  headers,
  target,
  { stripRemoteIdentityHeaders = false } = {},
) {
  const nextHeaders = {};
  for (const [key, value] of Object.entries(headers || {})) {
    const normalizedKey = key.toLowerCase();
    if (
      HOP_BY_HOP_HEADERS.has(normalizedKey)
      || normalizedKey === 'host'
      || normalizedKey === REMOTE_INGRESS_HEADER
      || (stripRemoteIdentityHeaders && isRemoteIdentityHeader(normalizedKey))
    ) {
      continue;
    }
    if (stripRemoteIdentityHeaders && normalizedKey === 'cookie') {
      const sanitizedCookie = stripCloudflareAccessCookie(value);
      if (sanitizedCookie) {
        nextHeaders[key] = sanitizedCookie;
      }
    } else {
      nextHeaders[key] = value;
    }
  }
  nextHeaders.host = target.port ? `${target.hostname}:${target.port}` : target.hostname;
  nextHeaders['x-mindscape-web-console-proxy'] = '1';
  if (stripRemoteIdentityHeaders) {
    nextHeaders[REMOTE_INGRESS_HEADER] = 'remote_workbench';
  }
  return nextHeaders;
}

export function copyProxyUpgradeHeaders(headers, target, options = {}) {
  const nextHeaders = copyProxyRequestHeaders(headers, target, options);
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
