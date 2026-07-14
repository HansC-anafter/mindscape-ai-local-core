'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Activity, RefreshCw, Video, VideoOff } from 'lucide-react';

import type { DeviceSessionEntry } from '@/lib/device-binding/deviceBindingClient';
import { refreshLiveMediaSessionAccess } from '@/lib/media-transport/liveMediaSessionClient';
import {
  getMediaReconnectDelayMs,
  hasMediaReconnectBudget,
} from '@/lib/media-transport/mediaReconnectPolicy';
import {
  startWhepPreview,
  type WhepPreviewHandle,
} from '@/lib/media-transport/whepPreviewClient';
import type { WebRTCSessionState } from '@/lib/media-transport/webrtcSessionTypes';
import type { MotionWindowAppendEvent } from './motionWindowAppendEvent';

interface PhoneSourcePreviewProps {
  apiUrl: string;
  workspaceId: string;
  session: DeviceSessionEntry;
  liveMotionSessionId?: string | null;
  onMotionWindowAppended?: (event: MotionWindowAppendEvent) => void;
  onLiveMotionSessionLost?: (liveSessionId: string) => void;
  className?: string;
}

function cn(...classes: Array<string | null | undefined | false>): string {
  return classes.filter(Boolean).join(' ');
}

export function PhoneSourcePreview({
  apiUrl,
  workspaceId,
  session,
  className,
}: PhoneSourcePreviewProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const handleRef = useRef<WhepPreviewHandle | null>(null);
  const reconnectAttemptRef = useRef(0);
  const [state, setState] = useState<WebRTCSessionState | 'idle' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const [hasRemoteStream, setHasRemoteStream] = useState(false);
  const [videoFrameReady, setVideoFrameReady] = useState(false);
  const supportsCamera = session.source_types.some((sourceType) => (
    sourceType === 'phone_camera'
    || sourceType === 'desktop_camera'
    || sourceType === 'usb_camera'
    || sourceType === 'virtual_camera'
    || sourceType === 'external_provider_camera'
  ));

  useEffect(() => {
    reconnectAttemptRef.current = 0;
  }, [session.media_session_id, session.session_id]);

  useEffect(() => {
    if (!supportsCamera || !session.media_session_id) {
      handleRef.current?.stop();
      handleRef.current = null;
      setState('idle');
      setNotice(supportsCamera ? 'Waiting for the source media session.' : null);
      setHasRemoteStream(false);
      setVideoFrameReady(false);
      return undefined;
    }
    let disposed = false;
    handleRef.current?.stop();
    handleRef.current = null;
    setState('idle');
    setError(null);
    setNotice('Connecting to the source media path.');
    setHasRemoteStream(false);
    setVideoFrameReady(false);

    void refreshLiveMediaSessionAccess({
      apiBase: apiUrl,
      workspaceId,
      deviceSessionId: session.session_id,
      mediaSessionId: session.media_session_id,
    }).then(async (access) => {
      if (disposed) {
        return;
      }
      const handle = await startWhepPreview({
        endpoint: access.session.endpoints.whep_preview_url,
        token: access.tokens.preview,
        onRemoteStream: (stream) => {
          if (disposed) {
            for (const track of stream.getTracks()) {
              track.stop();
            }
            return;
          }
          reconnectAttemptRef.current = 0;
          setHasRemoteStream(true);
          setVideoFrameReady(false);
          setNotice(null);
          setError(null);
          if (videoRef.current) {
            videoRef.current.srcObject = stream;
            void videoRef.current.play().catch(() => {
              setNotice('Video track connected; waiting for playback permission.');
            });
          }
        },
        onState: (nextState) => {
          if (!disposed) {
            setState(nextState);
          }
        },
        onError: (nextError) => {
          if (!disposed) {
            setError(nextError.message);
            setNotice(null);
            setState('error');
          }
        },
      });
      if (disposed) {
        handle.stop();
        return;
      }
      handleRef.current = handle;
    }).catch((nextError) => {
      if (!disposed) {
        setError(nextError instanceof Error ? nextError.message : 'whep_preview_failed');
        setNotice(null);
        setState('error');
      }
    });

    return () => {
      disposed = true;
      const handle = handleRef.current;
      handleRef.current = null;
      handle?.stop();
      if (videoRef.current) {
        videoRef.current.srcObject = null;
      }
    };
  }, [apiUrl, attempt, session.media_session_id, session.session_id, supportsCamera, workspaceId]);

  useEffect(() => {
    if (!supportsCamera || hasRemoteStream || state === 'idle' || state === 'error') {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      setNotice('Media path connected; waiting for the source video track.');
    }, 8000);
    return () => window.clearTimeout(timer);
  }, [hasRemoteStream, state, supportsCamera]);

  useEffect(() => {
    if (!supportsCamera || state !== 'error') {
      return undefined;
    }
    if (!hasMediaReconnectBudget(reconnectAttemptRef.current)) {
      setNotice('Preview reconnect limit reached. Keep the source open and reconnect preview.');
      return undefined;
    }
    const delayMs = getMediaReconnectDelayMs(reconnectAttemptRef.current);
    const timer = window.setTimeout(() => {
      reconnectAttemptRef.current += 1;
      setAttempt((current) => current + 1);
    }, delayMs);
    return () => window.clearTimeout(timer);
  }, [state, supportsCamera]);

  useEffect(() => {
    if (!supportsCamera || !hasRemoteStream || videoFrameReady || error) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      setNotice('Video track connected; waiting for camera frames.');
    }, 3500);
    return () => window.clearTimeout(timer);
  }, [error, hasRemoteStream, supportsCamera, videoFrameReady]);

  if (!supportsCamera) {
    return null;
  }

  const waitingForFrames = hasRemoteStream && !videoFrameReady && !error;
  const previewLabel = error
    || notice
    || (waitingForFrames ? 'video_track_waiting_for_frames' : state);
  const analysisLabel = session.media_session_id
    ? [
      `media ${session.media_session_state || 'ready'}`,
      session.media_receiver_metrics?.attempted_windows !== undefined
        ? `${session.media_receiver_metrics.accepted_windows || 0}`
          + `/${session.media_receiver_metrics.attempted_windows} windows`
        : 'Local Core analysis handoff',
      session.media_receiver_metrics?.failed_windows
        ? `${session.media_receiver_metrics.failed_windows} failed`
        : null,
    ].filter(Boolean).join(' · ')
    : 'media_session_pending';
  const fillAvailableHeight = className?.split(/\s+/).includes('h-full') ?? false;

  return (
    <div
      className={cn(
        'mt-2 overflow-hidden rounded-md border border-gray-200 bg-black dark:border-gray-700',
        className,
      )}
    >
      <div className={cn('relative w-full', fillAvailableHeight ? 'h-full min-h-0' : 'aspect-video')}>
        <video
          ref={videoRef}
          className="h-full w-full bg-black object-cover"
          autoPlay
          playsInline
          muted
          onLoadedData={() => setVideoFrameReady(true)}
          onCanPlay={() => setVideoFrameReady(true)}
          onPlaying={() => setVideoFrameReady(true)}
          data-testid={`phone-source-preview-${session.session_id}`}
        />
        <div className="absolute left-2 top-2 inline-flex max-w-[calc(100%-1rem)] items-center gap-1 rounded bg-black/70 px-2 py-1 text-[11px] font-medium text-white">
          {state === 'connected' || state === 'answer_received' ? (
            <Video className="h-3 w-3 shrink-0" aria-hidden="true" />
          ) : (
            <VideoOff className="h-3 w-3 shrink-0" aria-hidden="true" />
          )}
          <span className="truncate">{previewLabel}</span>
        </div>
        {(!hasRemoteStream && (notice || error)) || waitingForFrames ? (
          <div className="absolute inset-x-3 top-1/2 -translate-y-1/2 rounded-md bg-black/75 px-3 py-2 text-center text-xs font-medium text-white">
            <div>{previewLabel}</div>
            <button
              type="button"
              className="mt-2 inline-flex items-center gap-1 rounded border border-white/30 px-2 py-1 text-[11px] font-semibold text-white hover:bg-white/10"
              onClick={() => {
                reconnectAttemptRef.current = 0;
                setAttempt((current) => current + 1);
              }}
            >
              <RefreshCw className="h-3 w-3" aria-hidden="true" />
              Reconnect preview
            </button>
          </div>
        ) : null}
        <div
          className="absolute bottom-2 left-2 inline-flex max-w-[calc(100%-1rem)] items-center gap-1 rounded bg-black/70 px-2 py-1 text-[11px] font-medium text-white"
          data-testid={`phone-source-motion-status-${session.session_id}`}
        >
          <Activity className="h-3 w-3 shrink-0" aria-hidden="true" />
          <span className="truncate">{analysisLabel}</span>
        </div>
      </div>
    </div>
  );
}

export default PhoneSourcePreview;
