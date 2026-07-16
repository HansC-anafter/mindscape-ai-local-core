import { resolveExecutionPollingDelayMs, retryAfterMsFromError } from './executionPollingPolicy';

export type PollTimer = ReturnType<typeof setTimeout>;

export function scheduleExecutionPoll(
  callback: () => void,
  delayMs: number,
): PollTimer {
  return setTimeout(callback, Math.max(0, delayMs));
}

export function cancelExecutionPoll(timer: PollTimer | null): void {
  if (timer !== null) clearTimeout(timer);
}

export function executionDocumentHidden(): boolean {
  return typeof document !== 'undefined' && document.visibilityState === 'hidden';
}

export function startVisibilityAwarePollingLoop(options: {
  baseIntervalMs: number;
  run: (signal: AbortSignal) => Promise<void>;
  onError?: (error: unknown) => void;
}): () => void {
  let stopped = false;
  let timer: PollTimer | null = null;
  let controller: AbortController | null = null;
  let failures = 0;
  let retryAfterMs: number | null = null;

  const schedule = () => {
    if (stopped || executionDocumentHidden()) return;
    const delay = resolveExecutionPollingDelayMs({
      baseIntervalMs: options.baseIntervalMs,
      consecutiveFailures: failures,
      retryAfterMs,
    });
    timer = scheduleExecutionPoll(() => { void tick(); }, delay);
  };

  const tick = async () => {
    if (stopped || executionDocumentHidden() || controller) return;
    controller = new AbortController();
    try {
      await options.run(controller.signal);
      failures = 0;
      retryAfterMs = null;
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        failures += 1;
        retryAfterMs = retryAfterMsFromError(error);
        options.onError?.(error);
      }
    } finally {
      controller = null;
      schedule();
    }
  };

  const onVisibilityChange = () => {
    cancelExecutionPoll(timer);
    timer = null;
    if (executionDocumentHidden()) {
      controller?.abort();
      return;
    }
    void tick();
  };

  document.addEventListener('visibilitychange', onVisibilityChange);
  if (!executionDocumentHidden()) void tick();

  return () => {
    stopped = true;
    document.removeEventListener('visibilitychange', onVisibilityChange);
    cancelExecutionPoll(timer);
    controller?.abort();
  };
}
