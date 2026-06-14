'use client';

import { useEffect, useRef } from 'react';

import {
  fetchCompositionGraphRun,
  type CompositionGraphRun,
} from '@/lib/composition-graph';

type RunFetcher = (
  apiUrl: string,
  workspaceId: string,
  runId: string,
  signal?: AbortSignal,
) => Promise<{ run: CompositionGraphRun }>;

type StreamConnector = (
  runId: string,
  onRun: (run: CompositionGraphRun) => void,
  onDisconnect: () => void,
) => (() => void) | null;

interface RunMonitorOptions {
  apiUrl: string;
  workspaceId: string;
  onRun: (run: CompositionGraphRun) => void;
  onError: (error: Error) => void;
  fetchRun?: RunFetcher;
  streamConnector?: StreamConnector;
  maxMonitorMs?: number;
}

const TERMINAL_STATUSES = new Set(['succeeded', 'failed', 'canceled']);
const POLL_DELAYS_MS = [2000, 3000, 5000, 8000];
const HIDDEN_DELAY_MS = 10000;

export function useCompositionGraphRunMonitor({
  apiUrl,
  workspaceId,
  onRun,
  onError,
  fetchRun = fetchCompositionGraphRun,
  streamConnector,
  maxMonitorMs = 10 * 60 * 1000,
}: RunMonitorOptions) {
  const timerRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const disconnectStreamRef = useRef<(() => void) | null>(null);
  const generationRef = useRef(0);
  const onRunRef = useRef(onRun);
  const onErrorRef = useRef(onError);
  const fetchRunRef = useRef(fetchRun);
  const streamConnectorRef = useRef(streamConnector);

  onRunRef.current = onRun;
  onErrorRef.current = onError;
  fetchRunRef.current = fetchRun;
  streamConnectorRef.current = streamConnector;

  function stop() {
    generationRef.current += 1;
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    abortRef.current?.abort();
    abortRef.current = null;
    disconnectStreamRef.current?.();
    disconnectStreamRef.current = null;
  }

  function startPollingFallback(runId: string, startedAt = Date.now()) {
    const generation = generationRef.current;
    let attempt = 0;

    const poll = async () => {
      if (generation !== generationRef.current) {
        return;
      }
      if (Date.now() - startedAt >= maxMonitorMs) {
        stop();
        onErrorRef.current(new Error('Composition graph run monitor became stale.'));
        return;
      }
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const response = await fetchRunRef.current(
          apiUrl,
          workspaceId,
          runId,
          controller.signal,
        );
        if (generation !== generationRef.current) {
          return;
        }
        onRunRef.current(response.run);
        if (TERMINAL_STATUSES.has(response.run.status)) {
          stop();
          return;
        }
        attempt = Math.min(attempt + 1, POLL_DELAYS_MS.length - 1);
      } catch (cause) {
        if (controller.signal.aborted || generation !== generationRef.current) {
          return;
        }
        attempt = Math.min(attempt + 1, POLL_DELAYS_MS.length - 1);
      }
      const hidden = typeof document !== 'undefined' && document.visibilityState === 'hidden';
      const delay = hidden ? HIDDEN_DELAY_MS : POLL_DELAYS_MS[attempt];
      timerRef.current = window.setTimeout(poll, delay);
    };

    timerRef.current = window.setTimeout(poll, POLL_DELAYS_MS[0]);
  }

  function connectStream(runId: string): boolean {
    const connector = streamConnectorRef.current;
    if (!connector) {
      return false;
    }
    const generation = generationRef.current;
    const disconnect = connector(
      runId,
      (run) => {
        if (generation !== generationRef.current) {
          return;
        }
        onRunRef.current(run);
        if (TERMINAL_STATUSES.has(run.status)) {
          stop();
        }
      },
      () => {
        if (generation === generationRef.current) {
          disconnectStreamRef.current = null;
          startPollingFallback(runId);
        }
      },
    );
    if (!disconnect) {
      return false;
    }
    disconnectStreamRef.current = disconnect;
    return true;
  }

  function subscribe(run: CompositionGraphRun) {
    stop();
    onRunRef.current(run);
    if (TERMINAL_STATUSES.has(run.status)) {
      return;
    }
    if (!connectStream(run.id)) {
      startPollingFallback(run.id);
    }
  }

  useEffect(() => stop, []);

  return { subscribe, connectStream, startPollingFallback, stop };
}

