'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  openDeviceControlSocket,
  type DeviceControlEvent,
  type DeviceControlSocket,
} from '@/lib/device-binding/deviceBindingClient';
import { getApiBaseUrl } from '@/lib/api-url';
import { assessBrowserMediaCaptureReadiness } from '@/lib/media-transport/secureContextGuard';
import {
  startDesktopBrowserSourceSession,
  startPhoneBrowserSourceSession,
  type CameraFacingMode,
  type WebRTCSessionHandle,
  type WebRTCSessionState,
} from '@/lib/media-transport/webrtcSessionClient';
import {
  sourceKindLabel,
  type BrowserVideoInputSource,
  type CameraSourceKind,
} from '@/lib/media-transport/mediaDeviceCatalog';

export type SourceMode = 'phone' | 'camera';

export type LinkState =
  | 'idle'
  | 'connecting'
  | 'paired'
  | 'streaming'
  | 'closed'
  | 'secure_context_required'
  | 'error';

export type ReferenceLessonState = {
  chapter_ref?: string;
  title?: string;
  timestamp_ms?: number;
  poster_ref?: string;
  focus_cue?: string;
};

export interface DeviceLinkCaptureSessionOptions {
  pairingCode: string;
  workspaceId: string;
  initialSourceMode?: SourceMode;
}

function buildDeviceId(): string {
  const storageKey = 'mindscape_device_binding_id';
  if (typeof window === 'undefined') {
    return 'device_browser';
  }
  const existing = window.localStorage.getItem(storageKey);
  if (existing) {
    return existing;
  }
  const next = `browser_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  window.localStorage.setItem(storageKey, next);
  return next;
}

function stopStreamTracks(stream: MediaStream | null) {
  if (!stream) {
    return;
  }
  for (const track of stream.getTracks()) {
    track.stop();
  }
}

function isActiveLinkState(state: LinkState): boolean {
  return state === 'connecting' || state === 'paired' || state === 'streaming';
}

export function useDeviceLinkCaptureSession({
  pairingCode,
  workspaceId,
  initialSourceMode = 'phone',
}: DeviceLinkCaptureSessionOptions) {
  const [state, setState] = useState<LinkState>('idle');
  const [message, setMessage] = useState<string | null>(null);
  const [localStream, setLocalStream] = useState<MediaStream | null>(null);
  const [sourceMode, setSourceModeState] = useState<SourceMode>(
    initialSourceMode === 'camera' ? 'camera' : 'phone',
  );
  const [selectedCamera, setSelectedCamera] = useState<BrowserVideoInputSource | null>(null);
  const [mediaState, setMediaState] = useState<WebRTCSessionState | 'idle' | 'error'>('idle');
  const [phoneFacingMode, setPhoneFacingMode] = useState<CameraFacingMode>('environment');
  const [deviceSessionId, setDeviceSessionId] = useState<string | null>(null);
  const [referenceLessonState, setReferenceLessonState] = useState<ReferenceLessonState | null>(null);
  const [fullscreenSupported, setFullscreenSupported] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [fullscreenMessage, setFullscreenMessage] = useState<string | null>(null);

  const socketRef = useRef<DeviceControlSocket | null>(null);
  const mediaRef = useRef<WebRTCSessionHandle | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const captureRootRef = useRef<HTMLElement | null>(null);
  const apiUrl = useMemo(() => getApiBaseUrl(), []);
  const selectedCameraKind: CameraSourceKind = selectedCamera?.sourceKind || 'desktop_camera';
  const active = isActiveLinkState(state);

  useEffect(() => {
    streamRef.current = localStream;
    if (videoRef.current) {
      videoRef.current.srcObject = localStream;
    }
  }, [localStream]);

  useEffect(() => {
    const onFullscreenChange = () => {
      setIsFullscreen(document.fullscreenElement === captureRootRef.current);
      if (document.fullscreenElement === captureRootRef.current) {
        setFullscreenMessage(null);
      }
    };
    const onFullscreenError = () => {
      setFullscreenMessage('Fullscreen was blocked by this browser.');
    };
    setFullscreenSupported(
      typeof document !== 'undefined'
        && typeof document.documentElement.requestFullscreen === 'function',
    );
    document.addEventListener('fullscreenchange', onFullscreenChange);
    document.addEventListener('fullscreenerror', onFullscreenError);
    return () => {
      document.removeEventListener('fullscreenchange', onFullscreenChange);
      document.removeEventListener('fullscreenerror', onFullscreenError);
    };
  }, []);

  const stopMediaSession = useCallback(() => {
    mediaRef.current?.stop();
    mediaRef.current = null;
    stopStreamTracks(streamRef.current);
    streamRef.current = null;
    setLocalStream(null);
  }, []);

  useEffect(() => () => {
    stopMediaSession();
    socketRef.current?.close();
  }, [stopMediaSession]);

  const applyMediaState = useCallback((nextState: WebRTCSessionState) => {
    setMediaState(nextState);
    if (nextState === 'offer_sent' || nextState === 'answer_received' || nextState === 'connected') {
      setState('streaming');
    }
  }, []);

  const startMediaSession = useCallback(async (
    sessionId: string,
    facingMode: CameraFacingMode = phoneFacingMode,
  ) => {
    if (mediaRef.current) {
      return;
    }
    try {
      const baseInput = {
        apiBase: apiUrl,
        workspaceId,
        deviceSessionId: sessionId,
        mediaSessionId: sessionId,
        onLocalStream: setLocalStream,
        onState: applyMediaState,
        onError: (error: Error) => {
          setMediaState('error');
          setState('error');
          setMessage(error.message);
        },
      };
      mediaRef.current = sourceMode === 'phone'
        ? await startPhoneBrowserSourceSession({
            ...baseInput,
            audio: true,
            facingMode,
          })
        : await startDesktopBrowserSourceSession({
            ...baseInput,
            sourceKind: selectedCameraKind,
            deviceId: selectedCamera?.deviceId,
          });
    } catch (error) {
      setMediaState('error');
      setState('error');
      setMessage(error instanceof Error ? error.message : 'media_capture_failed');
    }
  }, [
    apiUrl,
    applyMediaState,
    phoneFacingMode,
    selectedCamera?.deviceId,
    selectedCameraKind,
    sourceMode,
    workspaceId,
  ]);

  const restartPhoneMediaSession = useCallback(async (nextFacingMode: CameraFacingMode) => {
    if (!deviceSessionId || sourceMode !== 'phone') {
      return;
    }
    stopMediaSession();
    setMediaState('idle');
    await startMediaSession(deviceSessionId, nextFacingMode);
  }, [deviceSessionId, sourceMode, startMediaSession, stopMediaSession]);

  const handleEvent = useCallback((event: DeviceControlEvent) => {
    if (event.type === 'reference_lesson_state') {
      setReferenceLessonState(event.reference_lesson_state || null);
      return;
    }
    if (event.type === 'session_paired' || event.type === 'heartbeat_ack') {
      setState('paired');
      setMessage(event.display_name || event.device_id || 'paired');
      if (event.session_id) {
        setDeviceSessionId(event.session_id);
        void startMediaSession(event.session_id);
      }
      return;
    }
    if (event.type === 'session_revoked' || event.type === 'session_closed' || event.type === 'session_expired') {
      setState('closed');
      setMessage(event.reason || event.type);
      setMediaState('closed');
      setDeviceSessionId(null);
      stopMediaSession();
      return;
    }
    if (event.type === 'session_error' || event.type === 'session_rejected') {
      setState('error');
      setMessage(event.reason || event.message || 'device_link_error');
    }
  }, [startMediaSession, stopMediaSession]);

  const connect = useCallback(() => {
    if (isActiveLinkState(state)) {
      return;
    }
    const readiness = assessBrowserMediaCaptureReadiness();
    if (!readiness.allowed) {
      setState(readiness.reason === 'secure_context_required' ? 'secure_context_required' : 'error');
      setMessage(readiness.message);
      return;
    }
    setState('connecting');
    setMessage(null);
    setMediaState('idle');
    setDeviceSessionId(null);
    stopMediaSession();
    socketRef.current?.close();
    const socket = openDeviceControlSocket({
      apiBase: apiUrl,
      workspaceId,
      pairingCode,
      onOpen: () => {
        socket.send({
          type: 'source_join',
          device_id: buildDeviceId(),
          display_name: sourceMode === 'phone'
            ? 'Phone camera'
            : sourceKindLabel(selectedCameraKind),
          source_types: sourceMode === 'phone'
            ? ['phone_camera', 'microphone']
            : [selectedCameraKind],
          metadata: {
            user_agent: typeof navigator === 'undefined' ? 'unknown' : navigator.userAgent,
            source_mode: sourceMode,
            ...(sourceMode === 'phone' ? { camera_facing_mode: phoneFacingMode } : {}),
          },
        });
      },
      onEvent: handleEvent,
      onError: (error) => {
        setState('error');
        setMessage(error.message);
      },
      onClose: () => {
        setState((current) => (current === 'paired' ? 'closed' : current));
      },
    });
    socketRef.current = socket;
  }, [
    apiUrl,
    handleEvent,
    pairingCode,
    phoneFacingMode,
    selectedCameraKind,
    sourceMode,
    state,
    stopMediaSession,
    workspaceId,
  ]);

  const setSourceMode = useCallback((nextSourceMode: SourceMode) => {
    if (isActiveLinkState(state)) {
      return;
    }
    setSourceModeState(nextSourceMode);
  }, [state]);

  const flipPhoneCamera = useCallback(async () => {
    const nextMode: CameraFacingMode = phoneFacingMode === 'environment' ? 'user' : 'environment';
    setPhoneFacingMode(nextMode);
    if (sourceMode === 'phone' && deviceSessionId && (state === 'paired' || state === 'streaming')) {
      await restartPhoneMediaSession(nextMode);
    }
  }, [deviceSessionId, phoneFacingMode, restartPhoneMediaSession, sourceMode, state]);

  const toggleFullscreen = useCallback(async () => {
    const root = captureRootRef.current;
    if (!root || !fullscreenSupported || typeof root.requestFullscreen !== 'function') {
      setFullscreenMessage('Fullscreen unavailable. The capture layout stays edge-to-edge.');
      return;
    }
    try {
      if (document.fullscreenElement === root) {
        await document.exitFullscreen();
      } else {
        await root.requestFullscreen();
      }
      setFullscreenMessage(null);
    } catch {
      setFullscreenMessage('Fullscreen was blocked by this browser.');
    }
  }, [fullscreenSupported]);

  const videoTrack = localStream?.getVideoTracks()[0] || null;
  const videoTrackLabel = videoTrack?.label || null;

  return {
    active,
    apiUrl,
    captureRootRef,
    connect,
    deviceSessionId,
    flipPhoneCamera,
    fullscreenMessage,
    fullscreenSupported,
    initialSourceMode,
    isFullscreen,
    localStream,
    mediaState,
    message,
    pairingCode,
    phoneFacingMode,
    referenceLessonState,
    selectedCamera,
    selectedCameraKind,
    setSelectedCamera,
    setSourceMode,
    sourceMode,
    state,
    toggleFullscreen,
    videoRef,
    videoTrackLabel,
    workspaceId,
  };
}
