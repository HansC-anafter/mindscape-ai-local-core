const FAILURE_DELAYS_MS = [10_000, 20_000, 30_000] as const;

export interface ExecutionPollingDelayInput {
  baseIntervalMs: number;
  consecutiveFailures: number;
  retryAfterMs?: number | null;
}

export function resolveExecutionPollingDelayMs(
  input: ExecutionPollingDelayInput,
): number {
  const base = Math.max(500, Number.isFinite(input.baseIntervalMs) ? input.baseIntervalMs : 10_000);
  const failureIndex = Math.max(0, Math.min(
    FAILURE_DELAYS_MS.length - 1,
    input.consecutiveFailures - 1,
  ));
  const failureDelay = input.consecutiveFailures > 0
    ? FAILURE_DELAYS_MS[failureIndex]
    : base;
  const retryAfter = Math.max(0, Number(input.retryAfterMs || 0));
  return Math.max(base, failureDelay, retryAfter);
}

export function retryAfterMsFromError(error: unknown): number | null {
  if (!error || typeof error !== 'object') return null;
  const candidate = Number((error as { retryAfterMs?: unknown }).retryAfterMs);
  return Number.isFinite(candidate) && candidate > 0 ? candidate : null;
}

export function retryAfterMsFromResponse(response: Response): number | null {
  const value = response.headers.get('Retry-After');
  if (!value) return null;
  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) return seconds * 1000;
  const epoch = Date.parse(value);
  if (!Number.isFinite(epoch)) return null;
  return Math.max(0, epoch - Date.now());
}
