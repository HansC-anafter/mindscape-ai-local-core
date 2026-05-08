const HOP_BY_HOP_HEADERS = [
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
];

const RETRYABLE_STATUSES = new Set([429, 502, 503, 504]);
const RETRYABLE_ERROR_CODES = new Set([
  'ECONNRESET',
  'ECONNREFUSED',
  'EHOSTUNREACH',
  'ENOTFOUND',
  'ETIMEDOUT',
]);

const DEFAULT_BACKEND_URL = 'http://backend:8200';
const DEFAULT_MEDIA_PROXY_URL = 'http://media-proxy:8000';
const MAX_IDEMPOTENT_ATTEMPTS = 3;
const RETRY_BASE_DELAY_MS = 150;
const RETRY_CAP_DELAY_MS = 1_000;

export interface ProxyUpstreamResolution {
  baseUrl: string;
  pathname: string;
  search: string;
}

export interface ProxyAttemptMeta {
  attempts: number;
  upstreamUrl: string;
}

export function normalizeBaseUrl(value: string | undefined, fallback: string): string {
  const resolved = value?.trim() || fallback;
  return resolved.replace(/\/+$/, '');
}

export function resolveApiProxyUpstream(requestUrl: string): ProxyUpstreamResolution {
  const url = new URL(requestUrl);
  const isMediaProxyPath = url.pathname.startsWith('/api/v1/media/');
  const baseUrl = isMediaProxyPath
    ? normalizeBaseUrl(process.env.MEDIA_PROXY_URL, DEFAULT_MEDIA_PROXY_URL)
    : normalizeBaseUrl(
        process.env.WEB_CONSOLE_BACKEND_URL ||
          process.env.BACKEND_URL ||
          process.env.NEXT_PUBLIC_BACKEND_URL,
        DEFAULT_BACKEND_URL
      );

  return {
    baseUrl,
    pathname: url.pathname,
    search: url.search,
  };
}

export function resolveBackendPathProxyUpstream(
  requestUrl: string,
  upstreamPathname: string
): ProxyUpstreamResolution {
  const url = new URL(requestUrl);
  return {
    baseUrl: normalizeBaseUrl(
      process.env.WEB_CONSOLE_BACKEND_URL ||
        process.env.BACKEND_URL ||
        process.env.NEXT_PUBLIC_BACKEND_URL,
      DEFAULT_BACKEND_URL
    ),
    pathname: upstreamPathname,
    search: url.search,
  };
}

function isIdempotentMethod(method: string): boolean {
  return method === 'GET' || method === 'HEAD';
}

function retryDelayMs(attemptIndex: number): number {
  return Math.min(RETRY_BASE_DELAY_MS * 2 ** attemptIndex, RETRY_CAP_DELAY_MS);
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function copyRequestHeaders(request: Request): Headers {
  const headers = new Headers(request.headers);
  for (const header of HOP_BY_HOP_HEADERS) {
    headers.delete(header);
  }
  headers.delete('host');
  headers.set('x-mindscape-web-console-proxy', '1');
  return headers;
}

function copyResponseHeaders(response: Response): Headers {
  const headers = new Headers(response.headers);
  for (const header of HOP_BY_HOP_HEADERS) {
    headers.delete(header);
  }
  headers.delete('content-length');
  headers.set('cache-control', 'no-store');
  return headers;
}

function transientFetchError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  const candidate = error as { code?: string; cause?: { code?: string }; name?: string };
  if (candidate.name === 'AbortError') return true;
  return Boolean(
    (candidate.code && RETRYABLE_ERROR_CODES.has(candidate.code)) ||
      (candidate.cause?.code && RETRYABLE_ERROR_CODES.has(candidate.cause.code))
  );
}

function upstreamUrlFromResolution(resolution: ProxyUpstreamResolution): string {
  return `${resolution.baseUrl}${resolution.pathname}${resolution.search}`;
}

async function readRequestBody(request: Request, method: string): Promise<ArrayBuffer | undefined> {
  if (method === 'GET' || method === 'HEAD') return undefined;
  const body = await request.arrayBuffer();
  return body.byteLength > 0 ? body : undefined;
}

export async function proxyToUpstream(
  request: Request,
  resolution: ProxyUpstreamResolution
): Promise<Response> {
  const method = request.method.toUpperCase();
  const idempotent = isIdempotentMethod(method);
  const maxAttempts = idempotent ? MAX_IDEMPOTENT_ATTEMPTS : 1;
  const upstreamUrl = upstreamUrlFromResolution(resolution);
  const requestBody = await readRequestBody(request, method);
  let lastError: unknown = null;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    try {
      const init: RequestInit = {
        method,
        headers: copyRequestHeaders(request),
        cache: 'no-store',
        redirect: 'manual',
      };
      if (requestBody) {
        init.body = requestBody;
      }

      const upstreamResponse = await fetch(upstreamUrl, init);
      if (
        idempotent &&
        RETRYABLE_STATUSES.has(upstreamResponse.status) &&
        attempt + 1 < maxAttempts
      ) {
        await upstreamResponse.body?.cancel();
        await sleep(retryDelayMs(attempt));
        continue;
      }

      return new Response(upstreamResponse.body, {
        status: upstreamResponse.status,
        statusText: upstreamResponse.statusText,
        headers: copyResponseHeaders(upstreamResponse),
      });
    } catch (error) {
      lastError = error;
      if (!idempotent || attempt + 1 >= maxAttempts || !transientFetchError(error)) {
        break;
      }
      await sleep(retryDelayMs(attempt));
    }
  }

  const code =
    lastError && typeof lastError === 'object'
      ? ((lastError as { code?: string; cause?: { code?: string } }).code ||
          (lastError as { cause?: { code?: string } }).cause?.code)
      : undefined;

  return Response.json(
    {
      error: 'backend_proxy_unavailable',
      upstream: upstreamUrl,
      code: code || 'UNKNOWN',
    },
    {
      status: 502,
      headers: {
        'Cache-Control': 'no-store',
      },
    }
  );
}
