'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Camera, CheckCircle2, Loader2, Video, XCircle } from 'lucide-react';

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
  type WebRTCSessionHandle,
  type WebRTCSessionState,
} from '@/lib/media-transport/webrtcSessionClient';
import {
  sourceKindLabel,
  type BrowserVideoInputSource,
  type CameraSourceKind,
} from '@/lib/media-transport/mediaDeviceCatalog';
import { DesktopSourcePicker } from '@/components/workspace/device-binding/DesktopSourcePicker';
import { DesktopSourcePreview } from '@/components/workspace/device-binding/DesktopSourcePreview';

type SourceMode = 'phone' | 'camera';

interface DeviceLinkPageClientProps {
  pairingCode: string;
  workspaceId?: string;
  initialSourceMode?: SourceMode;
}

type LinkState =
  | 'idle'
  | 'connecting'
  | 'paired'
  | 'streaming'
  | 'closed'
  | 'secure_context_required'
  | 'error';
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

export function DeviceLinkPageClient({
  pairingCode,
  workspaceId = 'default',
  initialSourceMode = 'phone',
}: DeviceLinkPageClientProps) {
  const [state, setState] = useState<LinkState>('idle');
  const [message, setMessage] = useState<string | null>(null);
  const socketRef = useRef<DeviceControlSocket | null>(null);
  const mediaRef = useRef<WebRTCSessionHandle | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [localStream, setLocalStream] = useState<MediaStream | null>(null);
  const [sourceMode, setSourceMode] = useState<SourceMode>(
    initialSourceMode === 'camera' ? 'camera' : 'phone',
  );
  const [selectedCamera, setSelectedCamera] = useState<BrowserVideoInputSource | null>(null);
  const [mediaState, setMediaState] = useState<WebRTCSessionState | 'idle' | 'error'>('idle');
  const apiUrl = useMemo(() => getApiBaseUrl(), []);
  const selectedCameraKind: CameraSourceKind = selectedCamera?.sourceKind || 'desktop_camera';

  useEffect(() => () => {
    mediaRef.current?.stop();
    socketRef.current?.close();
  }, []);

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.srcObject = localStream;
    }
  }, [localStream]);

  const applyMediaState = (nextState: WebRTCSessionState) => {
    setMediaState(nextState);
    if (nextState === 'offer_sent' || nextState === 'answer_received' || nextState === 'connected') {
      setState('streaming');
    }
  };

  const startMediaSession = async (sessionId: string) => {
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
  };

  const handleEvent = (event: DeviceControlEvent) => {
    if (event.type === 'session_paired' || event.type === 'heartbeat_ack') {
      setState('paired');
      setMessage(event.display_name || event.device_id || 'paired');
      if (event.session_id) {
        void startMediaSession(event.session_id);
      }
      return;
    }
    if (event.type === 'session_revoked' || event.type === 'session_closed' || event.type === 'session_expired') {
      setState('closed');
      setMessage(event.reason || event.type);
      setMediaState('closed');
      mediaRef.current?.stop();
      mediaRef.current = null;
      return;
    }
    if (event.type === 'session_error' || event.type === 'session_rejected') {
      setState('error');
      setMessage(event.reason || event.message || 'device_link_error');
    }
  };

  const connect = () => {
    if (state === 'connecting' || state === 'paired' || state === 'streaming') {
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
    mediaRef.current?.stop();
    mediaRef.current = null;
    setLocalStream(null);
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
  };

  const statusIcon = state === 'paired'
    ? <CheckCircle2 className="h-5 w-5 text-emerald-500" aria-hidden="true" />
    : state === 'streaming'
      ? <Video className="h-5 w-5 text-emerald-500" aria-hidden="true" />
    : state === 'error' || state === 'closed'
      ? <XCircle className="h-5 w-5 text-red-500" aria-hidden="true" />
      : <Camera className="h-5 w-5 text-sky-500" aria-hidden="true" />;

  return (
    <main className="min-h-screen bg-gray-950 text-gray-100">
      <div className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-5">
        <div className="rounded-lg border border-gray-800 bg-gray-900 p-5 shadow-2xl">
          <div className="mb-5 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gray-800">
              {statusIcon}
            </div>
            <div className="min-w-0">
              <h1 className="text-lg font-semibold">Motion source</h1>
              <p className="truncate text-sm text-gray-400">{state}</p>
            </div>
          </div>

          <div className="mb-5 rounded-md border border-gray-800 bg-gray-950 px-3 py-2 font-mono text-sm">
            {pairingCode}
          </div>

          <div className="mb-5 grid grid-cols-2 gap-2 rounded-md border border-gray-800 bg-gray-950 p-1">
            {([
              ['phone', 'Phone camera'],
              ['camera', 'Camera source'],
            ] as const).map(([mode, label]) => (
              <button
                key={mode}
                type="button"
                onClick={() => setSourceMode(mode)}
                disabled={state === 'connecting' || state === 'paired' || state === 'streaming'}
                className={`rounded px-3 py-2 text-sm font-semibold transition-colors ${
                  sourceMode === mode
                    ? 'bg-sky-500 text-white'
                    : 'text-gray-300 hover:bg-gray-900'
                } disabled:cursor-not-allowed disabled:opacity-70`}
              >
                {label}
              </button>
            ))}
          </div>

          {sourceMode === 'camera' ? (
            <DesktopSourcePicker
              selectedDeviceId={selectedCamera?.deviceId}
              onSelectionChange={setSelectedCamera}
              disabled={state === 'connecting' || state === 'paired' || state === 'streaming'}
            />
          ) : null}

          {message ? (
            <div className="mb-5 rounded-md border border-gray-800 bg-gray-950 px-3 py-2 text-sm text-gray-300">
              {message}
            </div>
          ) : null}

          {sourceMode === 'camera' ? (
            <DesktopSourcePreview
              stream={localStream}
              sourceKind={selectedCameraKind}
              state={mediaState}
              error={state === 'error' ? message : null}
            />
          ) : (
            <div className="mb-5 overflow-hidden rounded-md border border-gray-800 bg-black">
              <div className="aspect-video w-full">
                <video
                  ref={videoRef}
                  className="h-full w-full bg-black object-cover"
                  autoPlay
                  playsInline
                  muted
                  data-testid="device-link-local-preview"
                />
              </div>
            </div>
          )}

          <button
            type="button"
            onClick={connect}
            disabled={state === 'connecting' || state === 'paired' || state === 'streaming'}
            className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-sky-500 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-sky-600 disabled:cursor-not-allowed disabled:bg-gray-700 disabled:text-gray-400"
          >
            {state === 'connecting' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
            Connect
          </button>
        </div>
      </div>
    </main>
  );
}

export default DeviceLinkPageClient;
