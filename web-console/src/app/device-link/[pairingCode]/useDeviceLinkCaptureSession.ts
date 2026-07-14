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
  buildPhoneRelayVideoConstraints,
} from '@/lib/media-transport/relayMediaSourceSession';
import {
  stopLiveMediaSession,
  type LiveMediaSessionAccess,
} from '@/lib/media-transport/liveMediaSessionClient';
import {
  type CameraFacingMode,
  type CaptureOrientation,
  type WebRTCSessionHandle,
  type WebRTCSessionState,
} from '@/lib/media-transport/webrtcSessionTypes';
import { type BrowserVideoInputSource, type CameraSourceKind } from '@/lib/media-transport/mediaDeviceCatalog';
import {
  canReconnectMediaTransport,
  connectButtonLabel,
  connectionStatusDetail,
  connectionStatusLabel,
  isActiveLinkState,
  phoneFacingModeMessage,
  stopStreamTracks,
} from './useDeviceLinkCaptureSessionHelpers';
import { getMediaReconnectDelayMs, hasMediaReconnectBudget } from '@/lib/media-transport/mediaReconnectPolicy';
import { useDeviceControlHeartbeat } from './useDeviceControlHeartbeat';
import { useDeviceLinkFullscreen } from './useDeviceLinkFullscreen';
import { useSyncedMediaStreamRef } from './useSyncedMediaStreamRef';
import { buildDeviceLinkSourceJoinPayload } from './deviceLinkSourceJoinPayload';
import {
  applyPendingPhoneCaptureSettings,
  startDeviceLinkRelayMedia,
} from './deviceLinkRelayMedia';
import type { CaptureControlState, DeviceLinkCaptureSessionOptions, LinkState, ReferenceLessonState, SourceMode } from './useDeviceLinkCaptureSessionTypes';
import { useTrackedLinkState } from './useTrackedLinkState';

export type { CaptureControlState, DeviceLinkCaptureSessionOptions, LinkState, ReferenceLessonState, SourceMode } from './useDeviceLinkCaptureSessionTypes';

export function useDeviceLinkCaptureSession({
  pairingCode,
  workspaceId,
  initialSourceMode = 'phone',
}: DeviceLinkCaptureSessionOptions) {
  const { state, stateRef, setState: setLinkState } = useTrackedLinkState('idle');
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
  const [captureControlState, setCaptureControlState] = useState<CaptureControlState>('idle');

  const socketRef = useRef<DeviceControlSocket | null>(null);
  const mediaRef = useRef<WebRTCSessionHandle | null>(null);
  const mediaAccessRef = useRef<LiveMediaSessionAccess | null>(null);
  const mediaStartPromiseRef = useRef<Promise<void> | null>(null);
  const mediaStartTokenRef = useRef<symbol | null>(null);
  const mediaGenerationRef = useRef(0);
  const mediaReconnectAttemptRef = useRef(0);
  const suppressMediaErrorRef = useRef(false);
  const desiredPhoneFacingModeRef = useRef<CameraFacingMode>('environment');
  const desiredCaptureOrientationRef = useRef<CaptureOrientation>('portrait');
  const { streamRef, videoRef } = useSyncedMediaStreamRef(localStream);
  const apiUrl = useMemo(() => getApiBaseUrl(), []);
  const selectedCameraKind: CameraSourceKind = selectedCamera?.sourceKind || 'desktop_camera';
  const active = isActiveLinkState(state);
  const canReconnectMedia = canReconnectMediaTransport(state, mediaState, deviceSessionId);
  const {
    captureRootRef,
    fullscreenMessage,
    fullscreenSupported,
    isFullscreen,
    toggleFullscreen,
  } = useDeviceLinkFullscreen(setCaptureControlState);

  const stopMediaSession = useCallback(() => {
    mediaGenerationRef.current += 1;
    mediaRef.current?.stop();
    mediaRef.current = null;
    mediaStartPromiseRef.current = null;
    mediaStartTokenRef.current = null;
    stopStreamTracks(streamRef.current);
    streamRef.current = null;
    setLocalStream(null);
  }, []);

  const stopOwnedMediaSession = useCallback(() => {
    const access = mediaAccessRef.current;
    mediaAccessRef.current = null;
    stopMediaSession();
    if (access) {
      void stopLiveMediaSession({
        apiBase: apiUrl,
        workspaceId: access.session.workspace_id,
        deviceSessionId: access.session.device_session_id,
        mediaSessionId: access.session.media_session_id,
        keepalive: true,
      }).catch(() => undefined);
    }
  }, [apiUrl, stopMediaSession]);

  useEffect(() => () => {
    stopOwnedMediaSession();
    socketRef.current?.close();
  }, [stopOwnedMediaSession]);

  useDeviceControlHeartbeat({ deviceSessionId, socketRef, state });

  const applyMediaState = useCallback((nextState: WebRTCSessionState) => {
    if (nextState === 'answer_received' || nextState === 'connected') {
      mediaReconnectAttemptRef.current = 0;
    }
    if (nextState === 'local_stream_ready' || nextState === 'signal_open' || nextState === 'signal_joined') {
      setMessage(null);
    }
    if (nextState === 'closed') {
      setMessage('Camera media disconnected. Reconnect source media without changing the pairing code.');
    }
    setMediaState(nextState);
    if (nextState === 'offer_sent' || nextState === 'answer_received' || nextState === 'connected') {
      setLinkState('streaming');
    }
  }, [setLinkState]);

  const startMediaSession = useCallback(async (
    sessionId: string,
    facingMode: CameraFacingMode = phoneFacingMode,
  ) => {
    if (mediaRef.current || mediaStartPromiseRef.current) {
      return;
    }
    const startGeneration = mediaGenerationRef.current;
    const startToken = Symbol('media-start');
    mediaStartTokenRef.current = startToken;
    const startPromise = (async () => {
      try {
        const { access, handle: nextMedia } = await startDeviceLinkRelayMedia({
          apiBase: apiUrl,
          workspaceId,
          deviceSessionId: sessionId,
          sourceMode,
          selectedCameraKind,
          selectedCameraDeviceId: selectedCamera?.deviceId,
          facingMode,
          orientation: desiredCaptureOrientationRef.current,
          onLocalStream: setLocalStream,
          onState: (nextState) => {
            if (startGeneration === mediaGenerationRef.current) {
              applyMediaState(nextState);
            }
          },
          onError: (error) => {
            if (startGeneration !== mediaGenerationRef.current) return;
            if (error.message === 'unknown_device_session') {
              mediaReconnectAttemptRef.current = 0;
              setMediaState('error');
              setLinkState('closed');
              setDeviceSessionId(null);
              setMessage('The source control session is no longer active. Reconnect from this page.');
            } else if (suppressMediaErrorRef.current) {
              setMessage(error.message);
            } else {
              setMediaState('error');
              setLinkState('error');
              setMessage(error.message);
            }
          },
        });
        mediaAccessRef.current = access;
        if (startGeneration !== mediaGenerationRef.current) {
          nextMedia.stop();
          return;
        }
        mediaRef.current = nextMedia;
        await applyPendingPhoneCaptureSettings({
          handle: nextMedia,
          sourceMode,
          startingFacingMode: facingMode,
          desiredFacingMode: desiredPhoneFacingModeRef.current,
          startingOrientation: captureOrientation,
          desiredOrientation: desiredCaptureOrientationRef.current,
          onStream: (nextStream) => {
            streamRef.current = nextStream;
            setLocalStream(nextStream);
          },
        });
      } catch (error) {
        if (startGeneration === mediaGenerationRef.current) {
          setMediaState('error');
          setLinkState('error');
          setMessage(error instanceof Error ? error.message : 'media_capture_failed');
        }
      } finally {
        if (mediaStartTokenRef.current === startToken) {
          mediaStartTokenRef.current = null;
          mediaStartPromiseRef.current = null;
        }
      }
    })();
    mediaStartPromiseRef.current = startPromise;
    await startPromise;
  }, [
    apiUrl,
    applyMediaState,
    captureOrientation,
    phoneFacingMode,
    selectedCamera?.deviceId,
    selectedCameraKind,
    setLinkState,
    sourceMode,
    workspaceId,
  ]);

  useEffect(() => {
    if (!deviceSessionId || mediaState !== 'closed' || !isActiveLinkState(state)) {
      return undefined;
    }
    if (!hasMediaReconnectBudget(mediaReconnectAttemptRef.current)) {
      setMessage('Media signaling closed repeatedly. Open the workspace receiver, then reconnect this source.');
      return undefined;
    }
    const delayMs = getMediaReconnectDelayMs(mediaReconnectAttemptRef.current);
    const reconnectId = window.setTimeout(() => {
      if (!deviceSessionId || !isActiveLinkState(stateRef.current)) {
        return;
      }
      mediaReconnectAttemptRef.current += 1;
      stopMediaSession();
      setMediaState('idle');
      void startMediaSession(deviceSessionId);
    }, delayMs);
    return () => window.clearTimeout(reconnectId);
  }, [deviceSessionId, mediaState, startMediaSession, state, stopMediaSession]);

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
          buildPhoneRelayVideoConstraints(nextFacingMode),
          desiredCaptureOrientationRef.current === 'landscape'
            ? { orientation: desiredCaptureOrientationRef.current }
            : undefined,
        );
        streamRef.current = nextStream;
        setLocalStream(nextStream);
        setMessage(phoneFacingModeMessage(nextFacingMode));
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
      setMessage(phoneFacingModeMessage(nextFacingMode));
    } catch (error) {
      setMediaState('error');
      setLinkState('error');
      setMessage(error instanceof Error ? error.message : 'phone_camera_flip_failed');
    }
  }, [deviceSessionId, setLinkState, sourceMode, startMediaSession, stopMediaSession]);

  const handleEvent = useCallback((event: DeviceControlEvent) => {
    if (event.type === 'reference_lesson_state') {
      setReferenceLessonState(event.reference_lesson_state || null);
      return;
    }
    if (event.type === 'session_paired') {
      setLinkState('paired');
      setMessage('Connected. Keep this page open while the workspace receiver starts.');
      if (event.session_id) {
        setDeviceSessionId(event.session_id);
        void startMediaSession(event.session_id);
      }
      return;
    }
    if (event.type === 'heartbeat_ack') {
      setLinkState((current) => (current === 'streaming' ? 'streaming' : 'paired'));
      setMessage('Connected. Keep this page open while practice capture runs.');
      if (event.session_id) {
        setDeviceSessionId(event.session_id);
        void startMediaSession(event.session_id);
      }
      return;
    }
    if (event.type === 'session_revoked' || event.type === 'session_closed' || event.type === 'session_expired') {
      setLinkState('closed');
      setMessage(event.reason || event.type);
      setMediaState('closed');
      setDeviceSessionId(null);
      stopOwnedMediaSession();
      return;
    }
    if (event.type === 'session_error' || event.type === 'session_rejected') {
      setLinkState('error');
      setMessage(event.reason || event.message || 'device_link_error');
    }
  }, [setLinkState, startMediaSession, stopOwnedMediaSession]);

  const connect = useCallback(() => {
    if (isActiveLinkState(state)) {
      if (canReconnectMedia && deviceSessionId) {
        mediaReconnectAttemptRef.current = 0;
        setMessage('Reconnecting camera media.');
        stopMediaSession();
        setMediaState('idle');
        void startMediaSession(deviceSessionId);
      }
      return;
    }
    const readiness = assessBrowserMediaCaptureReadiness();
    if (!readiness.allowed) {
      setLinkState(readiness.reason === 'secure_context_required' ? 'secure_context_required' : 'error');
      setMessage(readiness.message);
      return;
    }
    setLinkState('connecting');
    setMessage(null);
    setMediaState('idle');
    setDeviceSessionId(null);
    mediaReconnectAttemptRef.current = 0;
    stopOwnedMediaSession();
    socketRef.current?.close();
    const socket = openDeviceControlSocket({
      apiBase: apiUrl,
      workspaceId,
      pairingCode,
      onOpen: () => {
        socket.send(buildDeviceLinkSourceJoinPayload({
          captureOrientation: desiredCaptureOrientationRef.current,
          phoneFacingMode,
          selectedCameraKind,
          sourceMode,
        }));
      },
      onEvent: handleEvent,
      onError: (error) => {
        setLinkState('error');
        setMessage(error.message);
      },
      onClose: () => {
        if (!isActiveLinkState(stateRef.current)) {
          return;
        }
        setLinkState('closed');
        setMessage('The source control connection closed. Reconnect from this page.');
        setMediaState('closed');
        setDeviceSessionId(null);
        stopOwnedMediaSession();
      },
    });
    socketRef.current = socket;
  }, [
    apiUrl,
    canReconnectMedia,
    deviceSessionId,
    handleEvent,
    pairingCode,
    captureOrientation,
    phoneFacingMode,
    selectedCameraKind,
    setLinkState,
    sourceMode,
    state,
    stopMediaSession,
    stopOwnedMediaSession,
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

  const videoTrack = localStream?.getVideoTracks()[0] || null;
  const videoTrackLabel = videoTrack?.label || null;

  return {
    active,
    apiUrl,
    canConnect: !active || canReconnectMedia,
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
