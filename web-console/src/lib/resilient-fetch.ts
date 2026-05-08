const DEFAULT_MAX_ATTEMPTS = 3;
const DEFAULT_RETRY_BASE_MS = 250;
const DEFAULT_RETRY_CAP_MS = 2_000;

const RETRYABLE_GET_STATUSES = new Set([429, 502, 503, 504]);
const RETRYABLE_ERROR_CODES = new Set([
  'ECONNRESET',
  'ECONNREFUSED',
  'EHOSTUNREACH',
  'ENOTFOUND',
  'ETIMEDOUT',
]);

type SharedFetchGlobal = typeof globalThis & {
  __mindscapeSharedGetInflight?: Map<string, Promise<Response>>;
};

export interface ResilientFetchOptions {
  dedupKey?: string;
  maxAttempts?: number;
  retryBaseMs?: number;
  retryCapMs?: number;
}

function sharedInflightGets(): Map<string, Promise<Response>> {
  const globalState = globalThis as SharedFetchGlobal;
  if (!globalState.__mindscapeSharedGetInflight) {
    globalState.__mindscapeSharedGetInflight = new Map();
  }
  return globalState.__mindscapeSharedGetInflight;
}

export function clearSharedGetInflightForTests(): void {
  sharedInflightGets().clear();
}

function methodFromInit(init?: RequestInit): string {
  return (init?.method || 'GET').toUpperCase();
}

function isSharedMethod(method: string): boolean {
  return method === 'GET' || method === 'HEAD';
}

function retryDelayMs(attemptIndex: number, options?: ResilientFetchOptions): number {
  const base = options?.retryBaseMs ?? DEFAULT_RETRY_BASE_MS;
  const cap = options?.retryCapMs ?? DEFAULT_RETRY_CAP_MS;
  return Math.min(base * 2 ** attemptIndex, cap);
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function errorCode(error: unknown): string | undefined {
  if (!error || typeof error !== 'object') return undefined;
  const candidate = error as { code?: string; cause?: { code?: string } };
  return candidate.code || candidate.cause?.code;
}

function shouldRetryFetchError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  const candidate = error as { name?: string };
  if (candidate.name === 'AbortError') return false;
  const code = errorCode(error);
  return candidate.name === 'TypeError' || Boolean(code && RETRYABLE_ERROR_CODES.has(code));
}

function headersKey(headers?: HeadersInit): string {
  if (!headers) return '';
  const normalized = new Headers(headers);
  const entries = Array.from(normalized.entries())
    .map(([key, value]) => [key.toLowerCase(), value] as const)
    .sort(([a], [b]) => a.localeCompare(b));
  return JSON.stringify(entries);
}

function requestKey(input: RequestInfo | URL, init?: RequestInit): string {
  const url = typeof input === 'string' || input instanceof URL ? String(input) : input.url;
  return `${methodFromInit(init)}:${url}:${headersKey(init?.headers)}`;
}

function abortIfNeeded(signal?: AbortSignal | null): void {
  if (!signal?.aborted) return;
  throw new DOMException('The operation was aborted.', 'AbortError');
}

export async function fetchWithIdempotentRetry(
  input: RequestInfo | URL,
  init: RequestInit = {},
  options?: ResilientFetchOptions
): Promise<Response> {
  const method = methodFromInit(init);
  const idempotent = isSharedMethod(method);
  const maxAttempts = idempotent ? options?.maxAttempts ?? DEFAULT_MAX_ATTEMPTS : 1;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    abortIfNeeded(init.signal);
    try {
      const response = await fetch(input, init);
      if (
        idempotent &&
        RETRYABLE_GET_STATUSES.has(response.status) &&
        attempt + 1 < maxAttempts
      ) {
        await response.body?.cancel();
        await sleep(retryDelayMs(attempt, options));
        continue;
      }
      return response;
    } catch (error) {
      if (!idempotent || attempt + 1 >= maxAttempts || !shouldRetryFetchError(error)) {
        throw error;
      }
      await sleep(retryDelayMs(attempt, options));
    }
  }

  return fetch(input, init);
}

export function sharedGetFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
  options?: ResilientFetchOptions
): Promise<Response> {
  const method = methodFromInit(init);
  if (!isSharedMethod(method)) {
    return fetchWithIdempotentRetry(input, init, options);
  }

  const key = options?.dedupKey || requestKey(input, init);
  const inflight = sharedInflightGets();
  const existing = inflight.get(key);
  if (existing) {
    return existing.then(response => response.clone());
  }

  const promise = fetchWithIdempotentRetry(input, init, options)
    .then(response => response.clone())
    .finally(() => {
      inflight.delete(key);
    });

  inflight.set(key, promise);
  return promise.then(response => response.clone());
}
