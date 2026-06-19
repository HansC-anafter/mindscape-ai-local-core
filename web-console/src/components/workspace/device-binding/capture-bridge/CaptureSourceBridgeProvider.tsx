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
  const referenceLessonStateRef = useRef<CaptureSourceReferenceLessonState | null>(null);
  const phonePublicOriginTouchedRef = useRef(false);

  useEffect(() => () => socketRef.current?.close(), []);

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

  const applyEvent = useCallback((event: DeviceControlEvent) => {
    if (event.type === 'reference_lesson_state') {
      const nextState = event.reference_lesson_state || null;
      referenceLessonStateRef.current = nextState;
      setReferenceLessonState(nextState);
      return;
    }
    if (event.type === 'pairing_ready') {
      setState('pairing');
    }
    if (event.type === 'session_paired') {
      setState('connected');
    }
    if (event.type === 'session_active') {
      setState(event.active_sessions?.length ? 'connected' : 'pairing');
    }
    if (event.type === 'session_revoked' || event.type === 'session_closed' || event.type === 'session_expired') {
      setState(event.active_sessions?.length ? 'connected' : 'pairing');
    }
    if (event.type === 'session_error' || event.type === 'session_rejected') {
      setState('error');
      setError(event.reason || event.message || 'device_binding_error');
    }
    if (event.active_sessions) {
      setSessions(sortSessions(event.active_sessions));
    }
    if (
      (event.type === 'session_paired' || event.type === 'session_active')
      && event.active_sessions?.length
      && referenceLessonStateRef.current
    ) {
      sendReferenceLessonState(referenceLessonStateRef.current);
    }
  }, [sendReferenceLessonState]);

  const startPairing = useCallback(async () => {
    if (disabled || state === 'creating') {
      return;
    }
    setState('creating');
    setError(null);
    setSessions([]);
    socketRef.current?.close();
    try {
      const nextPairing = await createDevicePairingCode({
        apiBase: apiUrl,
        workspaceId,
        expiresInSeconds: 600,
      });
      setPairing(nextPairing);
      const socket = openWorkspaceDeviceControlSocket({
        apiBase: apiUrl,
        workspaceId,
        onOpen: () => {
          socket.send({ type: 'workspace_subscribe' });
          if (referenceLessonStateRef.current) {
            sendReferenceLessonState(referenceLessonStateRef.current);
          }
        },
        onEvent: applyEvent,
        onError: (nextError) => {
          setError(nextError.message);
          setState('error');
        },
      });
      socketRef.current = socket;
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'device_pairing_failed');
      setState('error');
    }
  }, [apiUrl, applyEvent, disabled, state, workspaceId]);

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
