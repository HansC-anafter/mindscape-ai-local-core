import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { AddressableGraphSelection, AddressableObjectRef } from '@/lib/addressable-object-layer';
import {
  buildHostRuntimeStreamUrl,
  createHostRuntimeSession,
  fetchSharedCliBridgeServiceStatus,
  fetchHostRuntimeStatus,
  type HostRuntimeEvent,
  type SharedCliBridgeServiceStatus,
  type HostRuntimeSession,
  type HostRuntimeStatus,
  startSharedCliBridgeService,
  startHostRuntimeTurn,
} from '@/lib/host-runtime-sessions';

import { buildHostRuntimeGraphContext } from './hostRuntimeGraphContext';

export interface HostRuntimeRunSessionState {
  status: HostRuntimeStatus | null;
  session: HostRuntimeSession | null;
  events: HostRuntimeEvent[];
  bridgeService: SharedCliBridgeServiceStatus | null;
  isStarting: boolean;
  isStartingBridge: boolean;
  error: string | null;
  lastSeq: number;
}

export function useHostRuntimeRunSession({
  apiUrl,
  workspaceId,
  meetingId,
  selectedObjectRef,
  graphSelection,
}: {
  apiUrl: string;
  workspaceId: string;
  meetingId: string | null;
  selectedObjectRef: AddressableObjectRef | null;
  graphSelection?: AddressableGraphSelection | null;
}) {
  const [state, setState] = useState<HostRuntimeRunSessionState>({
    status: null,
    session: null,
    events: [],
    bridgeService: null,
    isStarting: false,
    isStartingBridge: false,
    error: null,
    lastSeq: 0,
  });
  const socketRef = useRef<WebSocket | null>(null);
  const selectedObjectUri = selectedObjectRef?.uri || null;
  const graphContext = useMemo(
    () => buildHostRuntimeGraphContext({
      workspaceId,
      meetingId,
      selectedObjectRef,
      graphSelection,
    }),
    [graphSelection, meetingId, selectedObjectRef, workspaceId],
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

  useEffect(() => {
    let cancelled = false;
    void fetchSharedCliBridgeServiceStatus({ apiUrl, workspaceId })
      .then((bridgeService) => {
        if (!cancelled) {
          setState((current) => ({ ...current, bridgeService }));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState((current) => ({ ...current, bridgeService: null }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [apiUrl, workspaceId]);

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
        selected_graph_anchor_uri: graphContext.selected_graph_anchor?.anchor_uri ?? null,
        graph_selection_hash: graphContext.graph_selection_ref.selection_hash,
        graph_selection_lens_code: graphContext.graph_selection_ref.lens_code,
        graph_context_id: graphContext.graph_context_ref.context_id,
        object_graph_aggregate_unit_ref: graphContext.object_graph_aggregate_unit_ref,
        object_graph_aggregate_unit_id: graphContext.object_graph_aggregate_unit.unit_id,
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
  }, [apiUrl, attachStream, graphContext, meetingId, selectedObjectUri, state.session, workspaceId]);

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
        contextRef: graphContext,
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
  }, [apiUrl, ensureSession, graphContext, workspaceId]);

  const startBridge = useCallback(async () => {
    setState((current) => ({ ...current, isStartingBridge: true, error: null }));
    try {
      const bridgeService = await startSharedCliBridgeService({ apiUrl, workspaceId });
      const status = await fetchHostRuntimeStatus(apiUrl);
      setState((current) => ({
        ...current,
        bridgeService,
        status,
        error: bridgeService.running ? null : (bridgeService.message || 'CLI bridge did not report ready.'),
      }));
    } catch (error) {
      setState((current) => ({
        ...current,
        error: error instanceof Error ? error.message : 'Failed to start CLI bridge.',
      }));
    } finally {
      setState((current) => ({ ...current, isStartingBridge: false }));
    }
  }, [apiUrl, workspaceId]);

  return {
    ...state,
    graphContext,
    startBridge,
    submitPrompt,
  };
}
