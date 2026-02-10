'use client';

import { useEffect, useRef, useCallback } from 'react';

interface SSEEventData {
  type: string;
  [key: string]: any;
}

type EventHandler = (data: SSEEventData) => void;

class ExecutionStreamManager {
  private streams: Map<string, EventSource> = new Map();
  private handlers: Map<string, Set<EventHandler>> = new Map();
  private refCounts: Map<string, number> = new Map();
  private streamUrls: Map<string, string> = new Map();
  private reconnectTimers: Map<string, ReturnType<typeof setTimeout>> = new Map();
  private reconnectAttempts: Map<string, number> = new Map();
  private connectionCallbacks: Map<string, Set<(connected: boolean) => void>> = new Map();
  private watchdogTimers: Map<string, ReturnType<typeof setTimeout>> = new Map();
  private watchdogFiredKeys: Set<string> = new Set();
  private static WATCHDOG_TIMEOUT_MS = 45_000;

  connect(executionId: string, streamUrl: string): () => void {
    const key = executionId;

    // Remember URL for reconnects
    this.streamUrls.set(key, streamUrl);

    // Increment ref count
    const currentCount = this.refCounts.get(key) || 0;
    this.refCounts.set(key, currentCount + 1);

    // If stream already exists, return cleanup function only
    if (this.streams.has(key)) {
      return () => {
        const count = this.refCounts.get(key) || 0;
        if (count <= 1) {
          this.fullDisconnect(key);
        } else {
          this.refCounts.set(key, count - 1);
        }
      };
    }

    // Create new EventSource (and allow reconnects on transient failures)
    const eventSource = this.createEventSource(key);
    this.streams.set(key, eventSource);

    eventSource.onopen = () => {
      // Connection established — clear watchdog fired flag
      this.watchdogFiredKeys.delete(key);
      this.reconnectAttempts.set(key, 0);
      this.notifyConnectionChange(key, true);
      this.resetWatchdog(key);
    };

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as SSEEventData;

        // Handle stream_end event
        if (data.type === 'stream_end') {
          this.fullDisconnect(key);
          return;
        }

        // Notify all handlers
        const handlers = this.handlers.get(key);
        if (handlers) {
          handlers.forEach(handler => {
            try {
              handler(data);
            } catch (err) {
              console.error(`[ExecutionStreamManager] Handler error for ${executionId}:`, err);
            }
          });
        }
      } catch (err) {
        console.error(`[ExecutionStreamManager] Failed to parse SSE message for ${executionId}:`, err);
      }
      // Reset watchdog on any message (including heartbeats)
      this.resetWatchdog(key);
    };

    eventSource.onerror = (error) => {
      const target = error.target as EventSource;
      if (target?.readyState === EventSource.CLOSED) {
        console.warn(`[ExecutionStreamManager] SSE connection closed for execution ${executionId}`);
        this.notifyConnectionChange(key, false);
        this.clearWatchdog(key);
        // Treat as transient: close current stream but keep handlers/refCounts and try to reconnect.
        this.closeStreamOnly(key);
        this.scheduleReconnect(key);
      } else if (target?.readyState === EventSource.CONNECTING) {
        // Reconnecting
      }
    };

    // Return cleanup function
    return () => {
      const count = this.refCounts.get(key) || 0;
      if (count <= 1) {
        this.fullDisconnect(key);
      } else {
        this.refCounts.set(key, count - 1);
      }
    };
  }

  subscribe(executionId: string, handler: EventHandler): () => void {
    const key = executionId;
    if (!this.handlers.has(key)) {
      this.handlers.set(key, new Set());
    }
    this.handlers.get(key)!.add(handler);

    // Return unsubscribe function
    return () => {
      const handlers = this.handlers.get(key);
      if (handlers) {
        handlers.delete(handler);
        if (handlers.size === 0) {
          this.handlers.delete(key);
        }
      }
    };
  }

  private closeStreamOnly(executionId: string): void {
    const key = executionId;
    const stream = this.streams.get(key);
    if (stream) {
      stream.close();
      this.streams.delete(key);
    }
  }

  private fullDisconnect(executionId: string): void {
    const key = executionId;

    const timer = this.reconnectTimers.get(key);
    if (timer) {
      clearTimeout(timer);
      this.reconnectTimers.delete(key);
    }
    this.reconnectAttempts.delete(key);
    this.streamUrls.delete(key);

    this.closeStreamOnly(key);
    this.handlers.delete(key);
    this.refCounts.delete(key);
    this.connectionCallbacks.delete(key);
    this.clearWatchdog(key);
  }

  private createEventSource(executionId: string): EventSource {
    const key = executionId;
    const url = this.streamUrls.get(key);
    if (!url) {
      throw new Error(`[ExecutionStreamManager] Missing stream URL for ${executionId}`);
    }
    return new EventSource(url);
  }

  private scheduleReconnect(executionId: string): void {
    const key = executionId;
    if (this.streams.has(key)) return;

    const count = this.refCounts.get(key) || 0;
    if (count <= 0) return;

    const url = this.streamUrls.get(key);
    if (!url) return;

    const prevTimer = this.reconnectTimers.get(key);
    if (prevTimer) {
      clearTimeout(prevTimer);
      this.reconnectTimers.delete(key);
    }

    const attempt = (this.reconnectAttempts.get(key) || 0) + 1;
    this.reconnectAttempts.set(key, attempt);

    // Exponential backoff with small jitter, capped at 30s.
    const baseMs = Math.min(30_000, 500 * Math.pow(2, Math.min(8, attempt)));
    const jitterMs = Math.floor(Math.random() * 250);
    const delayMs = baseMs + jitterMs;

    const timer = setTimeout(() => {
      // If still needed, recreate stream and keep handlers.
      const stillNeeded = (this.refCounts.get(key) || 0) > 0;
      if (!stillNeeded || this.streams.has(key)) return;

      try {
        const es = this.createEventSource(key);
        this.streams.set(key, es);

        es.onopen = () => {
          this.watchdogFiredKeys.delete(key);
          this.reconnectAttempts.set(key, 0);
          this.notifyConnectionChange(key, true);
          this.resetWatchdog(key);
        };

        es.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data) as SSEEventData;
            if (data.type === 'stream_end') {
              this.fullDisconnect(key);
              return;
            }
            const handlers = this.handlers.get(key);
            if (handlers) {
              handlers.forEach(handler => {
                try {
                  handler(data);
                } catch (err) {
                  console.error(`[ExecutionStreamManager] Handler error for ${executionId}:`, err);
                }
              });
            }
          } catch (err) {
            console.error(`[ExecutionStreamManager] Failed to parse SSE message for ${executionId}:`, err);
          }
          this.resetWatchdog(key);
        };

        es.onerror = (error) => {
          const target = error.target as EventSource;
          if (target?.readyState === EventSource.CLOSED) {
            console.warn(`[ExecutionStreamManager] SSE connection closed for execution ${executionId}`);
            this.notifyConnectionChange(key, false);
            this.clearWatchdog(key);
            this.closeStreamOnly(key);
            this.scheduleReconnect(key);
          }
        };
      } catch {
        this.scheduleReconnect(key);
      }
    }, delayMs);

    this.reconnectTimers.set(key, timer);
  }

  isConnected(executionId: string): boolean {
    const key = executionId;
    const stream = this.streams.get(key);
    return stream !== undefined && stream.readyState === EventSource.OPEN;
  }

  onConnectionChange(executionId: string, cb: (connected: boolean) => void): () => void {
    if (!this.connectionCallbacks.has(executionId)) {
      this.connectionCallbacks.set(executionId, new Set());
    }
    this.connectionCallbacks.get(executionId)!.add(cb);
    return () => { this.connectionCallbacks.get(executionId)?.delete(cb); };
  }

  private notifyConnectionChange(executionId: string, connected: boolean): void {
    this.connectionCallbacks.get(executionId)?.forEach(cb => {
      try { cb(connected); } catch (e) { /* ignore */ }
    });
  }

  private resetWatchdog(key: string): void {
    this.clearWatchdog(key);
    const timer = setTimeout(() => {
      // No message received within timeout — treat as stale connection
      // Only log on first timeout to avoid spam
      if (!this.watchdogFiredKeys.has(key)) {
        console.warn(`[ExecutionStreamManager] Watchdog timeout for ${key}, treating as disconnected`);
        this.watchdogFiredKeys.add(key);
      }
      this.notifyConnectionChange(key, false);
      this.closeStreamOnly(key);
      this.scheduleReconnect(key);
    }, ExecutionStreamManager.WATCHDOG_TIMEOUT_MS);
    this.watchdogTimers.set(key, timer);
  }

  private clearWatchdog(key: string): void {
    const timer = this.watchdogTimers.get(key);
    if (timer) {
      clearTimeout(timer);
      this.watchdogTimers.delete(key);
    }
  }
}

export const streamManager = new ExecutionStreamManager();

export function useExecutionStream(
  executionId: string | null | undefined,
  workspaceId: string,
  apiUrl: string,
  onEvent?: EventHandler
) {
  const unsubscribeRef = useRef<(() => void) | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);
  const onEventRef = useRef<EventHandler | undefined>(onEvent);

  // Keep ref in sync with latest callback
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    if (!executionId) {
      return;
    }

    const streamUrl = `${apiUrl}/api/v1/workspaces/${workspaceId}/executions/${executionId}/stream`;

    // Subscribe to events using ref to avoid re-subscribing on callback changes
    if (onEventRef.current) {
      // Unsubscribe previous handler if exists
      if (unsubscribeRef.current) {
        unsubscribeRef.current();
      }
      const unsubscribe = streamManager.subscribe(executionId, (data) => {
        // Call latest callback from ref
        if (onEventRef.current) {
          onEventRef.current(data);
        }
      });
      unsubscribeRef.current = unsubscribe;
    }

    // Connect to stream (returns cleanup function)
    const cleanup = streamManager.connect(executionId, streamUrl);
    cleanupRef.current = cleanup;

    // Cleanup on unmount or when executionId changes
    return () => {
      if (unsubscribeRef.current) {
        unsubscribeRef.current();
        unsubscribeRef.current = null;
      }
      if (cleanupRef.current) {
        cleanupRef.current();
        cleanupRef.current = null;
      }
    };
  }, [executionId, workspaceId, apiUrl]);

  const isConnected = executionId ? streamManager.isConnected(executionId) : false;

  return { isConnected };
}

