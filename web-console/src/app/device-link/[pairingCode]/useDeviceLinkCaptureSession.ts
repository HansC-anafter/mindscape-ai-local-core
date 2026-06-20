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
  buildPhoneVideoConstraints,
  startDesktopBrowserSourceSession,
  startPhoneBrowserSourceSession,
  type CameraFacingMode,
  type CaptureOrientation,
  type WebRTCSessionHandle,
  type WebRTCSessionState,
} from '@/lib/media-transport/webrtcSessionClient';
import {
  sourceKindLabel,
  type BrowserVideoInputSource,
  type CameraSourceKind,
} from '@/lib/media-transport/mediaDeviceCatalog';
import {
  buildDeviceId,
  connectButtonLabel,
  connectionStatusDetail,
  connectionStatusLabel,
  isActiveLinkState,
  stopStreamTracks,
} from './useDeviceLinkCaptureSessionHelpers';
import type {
  CaptureControlState,
  DeviceLinkCaptureSessionOptions,
  LinkState,
  ReferenceLessonState,
  SourceMode,
} from './useDeviceLinkCaptureSessionTypes';

export type {
  CaptureControlState,
  DeviceLinkCaptureSessionOptions,
  LinkState,
  ReferenceLessonState,
  SourceMode,
} from './useDeviceLinkCaptureSessionTypes';

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
  const [captureOrientation, setCaptureOrientation] = useState<CaptureOrientation>('portrait');
  const [deviceSessionId, setDeviceSessionId] = useState<string | null>(null);
  const [referenceLessonState, setReferenceLessonState] = useState<ReferenceLessonState | null>(null);
  const [fullscreenSupported, setFullscreenSupported] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [fullscreenMessage, setFullscreenMessage] = useState<string | null>(null);
  const [captureControlState, setCaptureControlState] = useState<CaptureControlState>('idle');

  const socketRef = useRef<DeviceControlSocket | null>(null);
  const mediaRef = useRef<WebRTCSessionHandle | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const suppressMediaErrorRef = useRef(false);
  const desiredPhoneFacingModeRef = useRef<CameraFacingMode>('environment');
  const desiredCaptureOrientationRef = useRef<CaptureOrientation>('portrait');
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
          if (suppressMediaErrorRef.current) {
            setMessage(error.message);
            return;
          }
          setMediaState('error');
          setState('error');
          setMessage(error.message);
        },
      };
      const nextMedia = sourceMode === 'phone'
        ? await startPhoneBrowserSourceSession({
            ...baseInput,
            audio: true,
            facingMode,
            videoOrientation: desiredCaptureOrientationRef.current,
          })
        : await startDesktopBrowserSourceSession({
            ...baseInput,
            sourceKind: selectedCameraKind,
            deviceId: selectedCamera?.deviceId,
          });
      mediaRef.current = nextMedia;
      const desiredFacingMode = desiredPhoneFacingModeRef.current;
      if (
        sourceMode === 'phone'
        && desiredFacingMode !== facingMode
        && nextMedia.replaceVideoTrack
      ) {
        const nextStream = await nextMedia.replaceVideoTrack(
          buildPhoneVideoConstraints(desiredFacingMode),
        );
        streamRef.current = nextStream;
        setLocalStream(nextStream);
      }
      const desiredCaptureOrientation = desiredCaptureOrientationRef.current;
      if (
        sourceMode === 'phone'
        && desiredCaptureOrientation !== captureOrientation
        && nextMedia.setVideoOrientation
      ) {
        const nextStream = await nextMedia.setVideoOrientation(desiredCaptureOrientation);
        streamRef.current = nextStream;
        setLocalStream(nextStream);
      }
    } catch (error) {
      setMediaState('error');
      setState('error');
      setMessage(error instanceof Error ? error.message : 'media_capture_failed');
    }
  }, [
    apiUrl,
    applyMediaState,
    captureOrientation,
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
    const currentMedia = mediaRef.current;
    if (!currentMedia) {
      return;
    }
    if (currentMedia.replaceVideoTrack) {
      suppressMediaErrorRef.current = true;
      try {
        const nextStream = await currentMedia.replaceVideoTrack(
          buildPhoneVideoConstraints(nextFacingMode),
          desiredCaptureOrientationRef.current === 'landscape'
            ? { orientation: desiredCaptureOrientationRef.current }
            : undefined,
        );
        streamRef.current = nextStream;
        setLocalStream(nextStream);
        setMessage(nextFacingMode === 'environment'
          ? 'Rear camera enabled.'
          : 'Front camera enabled.');
        return;
      } catch (error) {
        setMessage('Camera switch needed a media restart. Keep this page open.');
      } finally {
        suppressMediaErrorRef.current = false;
      }
    }
    stopMediaSession();
    setMediaState('idle');
    const beforeRestartHandle = mediaRef.current;
    try {
      await startMediaSession(deviceSessionId, nextFacingMode);
      if (!mediaRef.current || mediaRef.current === beforeRestartHandle) {
        return;
      }
      setMessage(nextFacingMode === 'environment'
        ? 'Rear camera enabled.'
        : 'Front camera enabled.');
    } catch (error) {
      setMediaState('error');
      setState('error');
      setMessage(error instanceof Error ? error.message : 'phone_camera_flip_failed');
    }
  }, [deviceSessionId, sourceMode, startMediaSession, stopMediaSession]);

  const handleEvent = useCallback((event: DeviceControlEvent) => {
    if (event.type === 'reference_lesson_state') {
      setReferenceLessonState(event.reference_lesson_state || null);
      return;
    }
    if (event.type === 'session_paired') {
      setState('paired');
      setMessage('Connected. Keep this page open while the workspace receiver starts.');
      if (event.session_id) {
        setDeviceSessionId(event.session_id);
        void startMediaSession(event.session_id);
      }
      return;
    }
    if (event.type === 'heartbeat_ack') {
      setState((current) => (current === 'streaming' ? 'streaming' : 'paired'));
      setMessage('Connected. Keep this page open while practice capture runs.');
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
            secure_context: Boolean(typeof window !== 'undefined' && window.isSecureContext),
            source_origin_scheme: typeof window === 'undefined'
              ? 'unknown'
              : window.location.protocol.replace(':', ''),
            capture_surface: 'device_link',
            ...(sourceMode === 'phone' ? {
              camera_facing_mode: phoneFacingMode,
              capture_orientation: desiredCaptureOrientationRef.current,
            } : {}),
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
    captureOrientation,
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
    desiredPhoneFacingModeRef.current = nextMode;
    setPhoneFacingMode(nextMode);
    if (sourceMode !== 'phone' || !deviceSessionId) {
      return;
    }
    setCaptureControlState('switching_camera');
    try {
      await restartPhoneMediaSession(nextMode);
    } finally {
      setCaptureControlState('idle');
    }
  }, [deviceSessionId, phoneFacingMode, restartPhoneMediaSession, sourceMode]);

  const toggleCaptureOrientation = useCallback(async () => {
    const nextOrientation: CaptureOrientation = captureOrientation === 'portrait' ? 'landscape' : 'portrait';
    const previousOrientation = captureOrientation;
    desiredCaptureOrientationRef.current = nextOrientation;
    setCaptureOrientation(nextOrientation);
    if (sourceMode !== 'phone' || !deviceSessionId) {
      return;
    }
    const currentMedia = mediaRef.current;
    if (!currentMedia?.setVideoOrientation) {
      desiredCaptureOrientationRef.current = previousOrientation;
      setCaptureOrientation(previousOrientation);
      setMessage('This browser cannot rotate the outgoing camera stream. Rotate the phone physically or reconnect.');
      return;
    }
    setCaptureControlState('switching_orientation');
    suppressMediaErrorRef.current = true;
    try {
      const nextStream = await currentMedia.setVideoOrientation(nextOrientation);
      streamRef.current = nextStream;
      setLocalStream(nextStream);
      setMessage(nextOrientation === 'portrait'
        ? 'Portrait capture enabled.'
        : 'Landscape capture enabled.');
    } catch (error) {
      desiredCaptureOrientationRef.current = previousOrientation;
      setCaptureOrientation(previousOrientation);
      setMessage(error instanceof Error
        ? `Capture orientation stayed ${previousOrientation}: ${error.message}`
        : `Capture orientation stayed ${previousOrientation}.`);
    } finally {
      suppressMediaErrorRef.current = false;
      setCaptureControlState('idle');
    }
  }, [captureOrientation, deviceSessionId, sourceMode]);

  const toggleFullscreen = useCallback(async () => {
    const root = captureRootRef.current;
    if (!root || !fullscreenSupported || typeof root.requestFullscreen !== 'function') {
      setFullscreenMessage('Fullscreen unavailable. The capture layout stays edge-to-edge.');
      return;
    }
    setCaptureControlState('fullscreen');
    try {
      if (document.fullscreenElement === root) {
        await document.exitFullscreen();
      } else {
        await root.requestFullscreen();
      }
      setFullscreenMessage(null);
    } catch {
      setFullscreenMessage('Fullscreen was blocked by this browser.');
    } finally {
      setCaptureControlState('idle');
    }
  }, [fullscreenSupported]);

  const videoTrack = localStream?.getVideoTracks()[0] || null;
  const videoTrackLabel = videoTrack?.label || null;

  return {
    active,
    apiUrl,
    canConnect: !active,
    captureControlBusy: captureControlState !== 'idle',
    captureControlState,
    captureRootRef,
    captureOrientation,
    connect,
    connectButtonLabel: connectButtonLabel(state, mediaState),
    connectionStatusDetail: connectionStatusDetail(state, mediaState),
    connectionStatusLabel: connectionStatusLabel(state, mediaState),
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
    toggleCaptureOrientation,
    videoRef,
    videoTrackLabel,
    workspaceId,
  };
}
