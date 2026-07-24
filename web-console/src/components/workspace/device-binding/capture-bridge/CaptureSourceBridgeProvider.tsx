'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

import {
  buildDeviceLinkHttpsHealthUrl,
  createDevicePairingCode,
  listActiveDeviceSessions,
  openWorkspaceDeviceControlSocket,
  revokeDeviceSession,
  type DeviceControlEvent,
  type DeviceControlSocket,
  type DevicePairingCode,
  type DeviceSessionEntry,
} from '@/lib/device-binding/deviceBindingClient';
import {
  assessDeviceLinkOriginReadiness,
  resolveDeviceLinkPublicOrigin,
  type DeviceLinkReadiness,
} from '@/lib/media-transport/deviceLinkReadiness';
import { createQrCodeSvgPath, type QrCodeSvgPath } from '@/lib/media-transport/qrCode';

type PanelState = 'idle' | 'creating' | 'pairing' | 'connected' | 'error';
type DeviceLinkSourceMode = 'phone' | 'camera';
export type CaptureSourceReferenceLessonState = NonNullable<
  DeviceControlEvent['reference_lesson_state']
>;

export interface CaptureSourceBridgeProviderProps {
  apiUrl: string;
  workspaceId: string;
  disabled?: boolean;
  children: ReactNode;
}

export interface CaptureSourceBridgeContextValue {
  apiUrl: string;
  workspaceId: string;
  disabled: boolean;
  state: PanelState;
  pairing: DevicePairingCode | null;
  sessions: DeviceSessionEntry[];
  error: string | null;
  referenceLessonState: CaptureSourceReferenceLessonState | null;
  phonePublicOrigin: string;
  phoneOrigin: string;
  phoneReadiness: DeviceLinkReadiness;
  phoneDeviceLink: string;
  phoneQrCode: QrCodeSvgPath | null;
  desktopDeviceLink: string;
  setPhonePublicOrigin: (origin: string) => void;
  publishReferenceLessonState: (state: CaptureSourceReferenceLessonState | null) => void;
  startPairing: () => Promise<void>;
  revokeSession: (sessionId: string) => Promise<void>;
}

const CaptureSourceBridgeContext = createContext<CaptureSourceBridgeContextValue | null>(null);
const WORKSPACE_SOCKET_RECONNECT_DELAY_MS = 1200;

function sortSessions(sessions: DeviceSessionEntry[]): DeviceSessionEntry[] {
  return [...sessions].sort((left, right) => left.created_at_epoch - right.created_at_epoch);
}

function buildDeviceLink(
  pairing: DevicePairingCode | null,
  workspaceId: string,
  sourceMode: DeviceLinkSourceMode,
  {
    publicOrigin,
    fallbackToWindowOrigin = true,
  }: {
    publicOrigin?: string;
    fallbackToWindowOrigin?: boolean;
  } = {},
): string {
  if (!pairing) {
    return '';
  }
  const fallbackPath = `${pairing.device_link_path}?workspaceId=${encodeURIComponent(workspaceId)}&sourceMode=${sourceMode}`;
  if (typeof window === 'undefined') {
    return fallbackPath;
  }
  const origin = publicOrigin?.trim() || (fallbackToWindowOrigin ? window.location.origin : '');
  if (!origin) {
    return '';
  }
  let url: URL;
  try {
    url = new URL(pairing.device_link_path, origin);
  } catch {
    return fallbackToWindowOrigin ? fallbackPath : '';
  }
  url.searchParams.set('workspaceId', workspaceId);
  url.searchParams.set('sourceMode', sourceMode);
  return url.toString();
}

export function CaptureSourceBridgeProvider({
  apiUrl,
  workspaceId,
  disabled = false,
  children,
}: CaptureSourceBridgeProviderProps) {
  const [state, setState] = useState<PanelState>('idle');
  const [pairing, setPairing] = useState<DevicePairingCode | null>(null);
  const [sessions, setSessions] = useState<DeviceSessionEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [referenceLessonState, setReferenceLessonState] =
    useState<CaptureSourceReferenceLessonState | null>(null);
  const [phonePublicOrigin, setPhonePublicOrigin] = useState('');
  const socketRef = useRef<DeviceControlSocket | null>(null);
  const socketKeyRef = useRef('');
  const reconnectTimerRef = useRef<number | null>(null);
  const openWorkspaceControlSocketRef = useRef<() => DeviceControlSocket | null>(() => null);
  const stateRef = useRef<PanelState>('idle');
  const pairingRef = useRef<DevicePairingCode | null>(null);
  const sessionsRef = useRef<DeviceSessionEntry[]>([]);
  const referenceLessonStateRef = useRef<CaptureSourceReferenceLessonState | null>(null);
  const phonePublicOriginTouchedRef = useRef(false);

  const clearWorkspaceReconnect = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const closeWorkspaceSocket = useCallback(() => {
    clearWorkspaceReconnect();
    const socket = socketRef.current;
    socketRef.current = null;
    socketKeyRef.current = '';
    socket?.close();
  }, [clearWorkspaceReconnect]);

  useEffect(() => () => closeWorkspaceSocket(), [closeWorkspaceSocket]);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    pairingRef.current = pairing;
  }, [pairing]);

  useEffect(() => {
    sessionsRef.current = sessions;
  }, [sessions]);

  useEffect(() => {
    referenceLessonStateRef.current = referenceLessonState;
  }, [referenceLessonState]);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof fetch !== 'function') {
      return;
    }
    const controller = new AbortController();
    void fetch(buildDeviceLinkHttpsHealthUrl({ apiBase: apiUrl }), {
      cache: 'no-store',
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          return null;
        }
        return response.json() as Promise<{ public_origin?: string | null }>;
      })
      .then((body) => {
        const publicOrigin = String(body?.public_origin || '').trim();
        if (!publicOrigin || phonePublicOriginTouchedRef.current) {
          return;
        }
        const browserOrigin = typeof window === 'undefined' ? '' : window.location.origin;
        if (assessDeviceLinkOriginReadiness(browserOrigin).state === 'ready') {
          return;
        }
        setPhonePublicOrigin((current) => current || publicOrigin);
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [apiUrl]);

  const fallbackBrowserOrigin = typeof window === 'undefined' ? '' : window.location.origin;
  const phoneOrigin = useMemo(() => resolveDeviceLinkPublicOrigin({
    overrideOrigin: phonePublicOrigin,
    fallbackOrigin: fallbackBrowserOrigin,
    allowFallbackLoopbackOnly: true,
    allowFallbackHttpsOrigin: true,
  }), [fallbackBrowserOrigin, phonePublicOrigin]);
  const phoneReadiness = useMemo(
    () => assessDeviceLinkOriginReadiness(phoneOrigin),
    [phoneOrigin],
  );
  const phoneDeviceLink = useMemo(() => (
    buildDeviceLink(pairing, workspaceId, 'phone', {
      publicOrigin: phoneOrigin,
      fallbackToWindowOrigin: false,
    })
  ), [pairing, phoneOrigin, workspaceId]);
  const phoneQrCode = useMemo(() => {
    if (!phoneReadiness.qrReady || !phoneDeviceLink) {
      return null;
    }
    try {
      return createQrCodeSvgPath(phoneDeviceLink);
    } catch {
      return null;
    }
  }, [phoneDeviceLink, phoneReadiness.qrReady]);
  const desktopDeviceLink = useMemo(() => (
    buildDeviceLink(pairing, workspaceId, 'camera')
  ), [pairing, workspaceId]);

  const sendReferenceLessonState = useCallback((nextState: CaptureSourceReferenceLessonState | null) => {
    socketRef.current?.send({
      type: 'reference_lesson_state',
      reference_lesson_state: nextState || {},
    });
  }, []);

  const applyActiveSessions = useCallback((
    activeSessions: DeviceSessionEntry[],
    { updateState = true }: { updateState?: boolean } = {},
  ) => {
    const nextSessions = sortSessions(activeSessions);
    const nextState = nextSessions.length ? 'connected' : pairingRef.current ? 'pairing' : 'idle';
    const sameSessions = sessionsRef.current.length === nextSessions.length
      && sessionsRef.current.every((session, index) => {
        const nextSession = nextSessions[index];
        return (
          nextSession
          && session.session_id === nextSession.session_id
          && session.state === nextSession.state
          && session.updated_at_epoch === nextSession.updated_at_epoch
          && session.expires_at_epoch === nextSession.expires_at_epoch
        );
      });
    if (sameSessions && (!updateState || stateRef.current === nextState)) {
      return;
    }
    sessionsRef.current = nextSessions;
    setSessions(nextSessions);
    if (updateState && stateRef.current !== nextState) {
      stateRef.current = nextState;
      setState(nextState);
    }
    if (nextSessions.length) {
      setError(null);
    }
  }, []);

  const hydrateActiveSessions = useCallback(async () => {
    if (disabled) {
      return;
    }
    try {
      const activeSessions = await listActiveDeviceSessions({
        apiBase: apiUrl,
        workspaceId,
      });
      applyActiveSessions(activeSessions);
    } catch {
      // The websocket path remains authoritative when REST hydration is unavailable.
    }
  }, [apiUrl, applyActiveSessions, disabled, workspaceId]);

  const applyEvent = useCallback((event: DeviceControlEvent) => {
    if (event.type === 'reference_lesson_state') {
      const nextState = event.reference_lesson_state || null;
      referenceLessonStateRef.current = nextState;
      setReferenceLessonState(nextState);
      return;
    }
    if (event.type === 'pairing_ready') {
      setError(null);
      setState('pairing');
    }
    if (event.type === 'session_paired') {
      setError(null);
      setState('connected');
    }
    if (event.type === 'session_active') {
      setError(null);
      setState(
        event.active_sessions?.length ? 'connected' : pairingRef.current ? 'pairing' : 'idle',
      );
    }
    if (event.type === 'session_revoked' || event.type === 'session_closed' || event.type === 'session_expired') {
      setState(
        event.active_sessions?.length ? 'connected' : pairingRef.current ? 'pairing' : 'idle',
      );
    }
    if (event.type === 'session_error' || event.type === 'session_rejected') {
      setState('error');
      setError(event.reason || event.message || 'device_binding_error');
    }
    if (event.active_sessions) {
      applyActiveSessions(event.active_sessions, {
        updateState: event.type !== 'session_error' && event.type !== 'session_rejected',
      });
    }
    if (
      (event.type === 'session_paired' || event.type === 'session_active')
      && event.active_sessions?.length
      && referenceLessonStateRef.current
    ) {
      sendReferenceLessonState(referenceLessonStateRef.current);
    }
  }, [applyActiveSessions, sendReferenceLessonState]);

  const scheduleWorkspaceReconnect = useCallback(() => {
    if (disabled || reconnectTimerRef.current !== null) {
      return;
    }
    reconnectTimerRef.current = window.setTimeout(() => {
      reconnectTimerRef.current = null;
      openWorkspaceControlSocketRef.current();
    }, WORKSPACE_SOCKET_RECONNECT_DELAY_MS);
  }, [disabled]);

  const openWorkspaceControlSocket = useCallback(() => {
    if (disabled) {
      return null;
    }
    const socketKey = `${apiUrl}\n${workspaceId}`;
    if (socketRef.current && socketKeyRef.current === socketKey) {
      return socketRef.current;
    }
    socketRef.current?.close();
    socketKeyRef.current = socketKey;
    const socket = openWorkspaceDeviceControlSocket({
      apiBase: apiUrl,
      workspaceId,
      onOpen: () => {
        socket.send({ type: 'workspace_subscribe' });
        void hydrateActiveSessions();
        if (referenceLessonStateRef.current) {
          sendReferenceLessonState(referenceLessonStateRef.current);
        }
      },
      onEvent: applyEvent,
      onError: (nextError) => {
        setError(nextError.message);
        setState('error');
      },
      onClose: () => {
        if (socketRef.current === socket) {
          socketRef.current = null;
          socketKeyRef.current = '';
          void hydrateActiveSessions();
          scheduleWorkspaceReconnect();
        }
      },
    });
    socketRef.current = socket;
    return socket;
  }, [apiUrl, applyEvent, disabled, hydrateActiveSessions, scheduleWorkspaceReconnect, sendReferenceLessonState, workspaceId]);

  useEffect(() => {
    openWorkspaceControlSocketRef.current = openWorkspaceControlSocket;
  }, [openWorkspaceControlSocket]);

  useEffect(() => {
    if (disabled) {
      closeWorkspaceSocket();
      return undefined;
    }
    openWorkspaceControlSocket();
    void hydrateActiveSessions();
    return undefined;
  }, [closeWorkspaceSocket, disabled, hydrateActiveSessions, openWorkspaceControlSocket]);

  const startPairing = useCallback(async () => {
    if (disabled || state === 'creating') {
      return;
    }
    setState('creating');
    setError(null);
    try {
      const nextPairing = await createDevicePairingCode({
        apiBase: apiUrl,
        workspaceId,
        expiresInSeconds: 600,
      });
      pairingRef.current = nextPairing;
      setPairing(nextPairing);
      openWorkspaceControlSocket();
      setState(sessionsRef.current.length ? 'connected' : 'pairing');
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'device_pairing_failed');
      setState('error');
    }
  }, [apiUrl, disabled, openWorkspaceControlSocket, state, workspaceId]);

  const revokeSession = useCallback(async (sessionId: string) => {
    try {
      await revokeDeviceSession({
        apiBase: apiUrl,
        workspaceId,
        sessionId,
      });
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'device_revoke_failed');
      setState('error');
    }
  }, [apiUrl, workspaceId]);

  const setPhonePublicOriginValue = useCallback((origin: string) => {
    phonePublicOriginTouchedRef.current = true;
    setPhonePublicOrigin(origin);
  }, []);

  const publishReferenceLessonState = useCallback((nextState: CaptureSourceReferenceLessonState | null) => {
    referenceLessonStateRef.current = nextState;
    setReferenceLessonState(nextState);
    sendReferenceLessonState(nextState);
  }, [sendReferenceLessonState]);

  const value = useMemo<CaptureSourceBridgeContextValue>(() => ({
    apiUrl,
    workspaceId,
    disabled,
    state,
    pairing,
    sessions,
    error,
    referenceLessonState,
    phonePublicOrigin,
    phoneOrigin,
    phoneReadiness,
    phoneDeviceLink,
    phoneQrCode,
    desktopDeviceLink,
    setPhonePublicOrigin: setPhonePublicOriginValue,
    publishReferenceLessonState,
    startPairing,
    revokeSession,
  }), [
    apiUrl,
    desktopDeviceLink,
    disabled,
    error,
    pairing,
    phoneDeviceLink,
    phoneOrigin,
    phonePublicOrigin,
    phoneQrCode,
    phoneReadiness,
    publishReferenceLessonState,
    referenceLessonState,
    revokeSession,
    sessions,
    setPhonePublicOriginValue,
    startPairing,
    state,
    workspaceId,
  ]);

  return (
    <CaptureSourceBridgeContext.Provider value={value}>
      {children}
    </CaptureSourceBridgeContext.Provider>
  );
}

export function useCaptureSourceBridge(): CaptureSourceBridgeContextValue {
  const value = useContext(CaptureSourceBridgeContext);
  if (!value) {
    throw new Error('useCaptureSourceBridge must be used within CaptureSourceBridgeProvider');
  }
  return value;
}

export function useOptionalCaptureSourceBridge(): CaptureSourceBridgeContextValue | null {
  return useContext(CaptureSourceBridgeContext);
}
