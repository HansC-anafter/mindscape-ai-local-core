import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { AddressableObjectRef } from '@/lib/addressable-object-layer';
import {
  buildHostRuntimeStreamUrl,
  createHostRuntimeSession,
  fetchHostRuntimeStatus,
  type HostRuntimeEvent,
  type HostRuntimeSession,
  type HostRuntimeStatus,
  startHostRuntimeTurn,
} from '@/lib/host-runtime-sessions';

export interface HostRuntimeRunSessionState {
  status: HostRuntimeStatus | null;
  session: HostRuntimeSession | null;
  events: HostRuntimeEvent[];
  isStarting: boolean;
  error: string | null;
  lastSeq: number;
}

export function useHostRuntimeRunSession({
  apiUrl,
  workspaceId,
  meetingId,
  selectedObjectRef,
}: {
  apiUrl: string;
  workspaceId: string;
  meetingId: string | null;
  selectedObjectRef: AddressableObjectRef | null;
}) {
  const [state, setState] = useState<HostRuntimeRunSessionState>({
    status: null,
    session: null,
    events: [],
    isStarting: false,
    error: null,
    lastSeq: 0,
  });
  const socketRef = useRef<WebSocket | null>(null);
  const selectedObjectUri = selectedObjectRef?.uri || null;
  const contextRef = useMemo(
    () => ({
      meeting_id: meetingId,
      selected_object_ref: selectedObjectRef,
      source: 'aol_graph_runtime_runs',
    }),
    [meetingId, selectedObjectRef],
  );

  useEffect(() => {
    let cancelled = false;
    void fetchHostRuntimeStatus(apiUrl)
      .then((status) => {
        if (!cancelled) {
          setState((current) => ({ ...current, status }));
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setState((current) => ({
            ...current,
            error: error instanceof Error ? error.message : 'Failed to load host runtime status.',
          }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [apiUrl]);

  const attachStream = useCallback((session: HostRuntimeSession, lastSeq: number) => {
    if (typeof WebSocket === 'undefined') {
      return;
    }
    socketRef.current?.close();
    const socket = new WebSocket(buildHostRuntimeStreamUrl({
      apiUrl,
      workspaceId,
      sessionId: session.id,
      lastSeq,
    }));
    socketRef.current = socket;
    socket.onmessage = (message) => {
      try {
        const payload = JSON.parse(String(message.data));
        if (payload.type !== 'event' || !payload.event) {
          return;
        }
        const event = payload.event as HostRuntimeEvent;
        setState((current) => ({
          ...current,
          events: [...current.events.filter((existing) => existing.seq !== event.seq || event.seq == null), event],
          lastSeq: Math.max(current.lastSeq, Number(event.seq || 0)),
        }));
      } catch {
        // Ignore malformed stream frames; REST snapshot remains the source for replay.
      }
    };
    socket.onerror = () => {
      setState((current) => ({ ...current, error: 'Host runtime stream connection failed.' }));
    };
  }, [apiUrl, workspaceId]);

  useEffect(() => {
    return () => {
      socketRef.current?.close();
    };
  }, []);

  const ensureSession = useCallback(async (): Promise<HostRuntimeSession> => {
    if (state.session) {
      return state.session;
    }
    const session = await createHostRuntimeSession({
      apiUrl,
      workspaceId,
      cwd: '/workspace',
      metadata: {
        meeting_id: meetingId,
        selected_object_uri: selectedObjectUri,
      },
    });
    setState((current) => ({
      ...current,
      session,
      error: null,
      lastSeq: session.last_event_seq || 0,
    }));
    attachStream(session, session.last_event_seq || 0);
    return session;
  }, [apiUrl, attachStream, meetingId, selectedObjectUri, state.session, workspaceId]);

  const submitPrompt = useCallback(async (prompt: string) => {
    const trimmed = prompt.trim();
    if (!trimmed) {
      return;
    }
    setState((current) => ({ ...current, isStarting: true, error: null }));
    try {
      const session = await ensureSession();
      const result = await startHostRuntimeTurn({
        apiUrl,
        workspaceId,
        sessionId: session.id,
        prompt: trimmed,
        contextRef,
      });
      if (result.event) {
        setState((current) => ({
          ...current,
          events: [...current.events, result.event!],
          lastSeq: Math.max(current.lastSeq, Number(result.event!.seq || 0)),
        }));
      }
    } catch (error) {
      setState((current) => ({
        ...current,
        error: error instanceof Error ? error.message : 'Failed to start host runtime turn.',
      }));
    } finally {
      setState((current) => ({ ...current, isStarting: false }));
    }
  }, [apiUrl, contextRef, ensureSession, workspaceId]);

  return {
    ...state,
    submitPrompt,
  };
}
