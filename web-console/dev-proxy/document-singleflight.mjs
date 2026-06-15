export const DEFAULT_FRONTEND_DOCUMENT_SINGLEFLIGHT_MAX_BODY_BYTES = 4 * 1024 * 1024;

const FRONTEND_DOCUMENT_ASSET_PATTERN = /\.(?:avif|css|gif|ico|jpeg|jpg|js|json|map|mjs|mp4|otf|png|svg|ttf|txt|wasm|webm|webp|woff|woff2)$/i;
const FRONTEND_DOCUMENT_EXCLUDED_PATHS = new Set([
  '/favicon.ico',
  '/manifest.json',
  '/robots.txt',
  '/site.webmanifest',
]);

function parseRequestUrl(requestUrl = '/') {
  try {
    return new URL(requestUrl, 'http://localhost');
  } catch {
    return new URL('/', 'http://localhost');
  }
}

export function isFrontendDocumentRequest(method = 'GET', requestUrl = '/') {
  if (String(method || 'GET').toUpperCase() !== 'GET') {
    return false;
  }

  const parsed = parseRequestUrl(requestUrl);
  const { pathname } = parsed;
  if (pathname === '/') {
    return true;
  }
  if (
    pathname.startsWith('/api/')
    || pathname.startsWith('/_next/')
    || pathname.startsWith('/static/')
    || pathname.startsWith('/ui-assets/')
    || FRONTEND_DOCUMENT_EXCLUDED_PATHS.has(pathname)
    || FRONTEND_DOCUMENT_ASSET_PATTERN.test(pathname)
  ) {
    return false;
  }
  return pathname.startsWith('/workspaces/');
}

export function normalizeFrontendDocumentSingleflightKey(method = 'GET', requestUrl = '/') {
  if (!isFrontendDocumentRequest(method, requestUrl)) {
    return null;
  }

  const parsed = parseRequestUrl(requestUrl);
  return `GET:${parsed.pathname}${parsed.search}`;
}

export function createFrontendDocumentSingleflight() {
  const inflight = new Map();

  return {
    clear() {
      inflight.clear();
    },
    get size() {
      return inflight.size;
    },
    run(method, requestUrl, producer) {
      const key = normalizeFrontendDocumentSingleflightKey(method, requestUrl);
      if (!key) {
        return {
          handled: false,
          key: null,
          shared: false,
          promise: Promise.resolve().then(producer),
        };
      }

      const existing = inflight.get(key);
      if (existing) {
        return {
          handled: true,
          key,
          shared: true,
          promise: existing,
        };
      }

      const pending = Promise.resolve()
        .then(producer)
        .finally(() => {
          inflight.delete(key);
        });
      inflight.set(key, pending);
      return {
        handled: true,
        key,
        shared: false,
        promise: pending,
      };
    },
  };
}
