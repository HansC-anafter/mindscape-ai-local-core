'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Activity, RefreshCw, Video, VideoOff } from 'lucide-react';

import type { DeviceSessionEntry } from '@/lib/device-binding/deviceBindingClient';
import {
  startWorkspaceReceiverSession,
  type WebRTCSessionHandle,
  type WebRTCSessionState,
} from '@/lib/media-transport/webrtcSessionClient';
import {
  createBrowserMediaPipePoseAdapter,
  createLivePoseWindowController,
  type LivePoseWindowController,
  type LivePoseWindowControllerStatus,
} from '@/lib/motion-analysis/livePoseWindow';
import { appendMotionWindow } from '@/lib/motion-analysis/motionWindowClient';
import type { MotionWindowAppendEvent } from './motionWindowAppendEvent';

interface PhoneSourcePreviewProps {
  apiUrl: string;
  workspaceId: string;
  session: DeviceSessionEntry;
  liveMotionSessionId?: string | null;
  onMotionWindowAppended?: (event: MotionWindowAppendEvent) => void;
  className?: string;
}

function cn(...classes: Array<string | null | undefined | false>): string {
  return classes.filter(Boolean).join(' ');
}

export function PhoneSourcePreview({
  apiUrl,
  workspaceId,
  session,
  liveMotionSessionId = null,
  onMotionWindowAppended,
  className,
}: PhoneSourcePreviewProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const handleRef = useRef<WebRTCSessionHandle | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const motionControllerRef = useRef<LivePoseWindowController | null>(null);
  const startMotionAnalysisRef = useRef<() => void>(() => undefined);
  const [state, setState] = useState<WebRTCSessionState | 'idle' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [receiverAttempt, setReceiverAttempt] = useState(0);
  const [receiverNotice, setReceiverNotice] = useState<string | null>(null);
  const [hasRemoteStream, setHasRemoteStream] = useState(false);
  const [videoFrameReady, setVideoFrameReady] = useState(false);
  const [motionStatus, setMotionStatus] = useState<LivePoseWindowControllerStatus>({
    state: 'idle',
    appendedWindowCount: 0,
  });
  const supportsCamera = session.source_types.some((sourceType) => (
    sourceType === 'phone_camera' ||
    sourceType === 'desktop_camera' ||
    sourceType === 'usb_camera' ||
    sourceType === 'virtual_camera' ||
    sourceType === 'external_provider_camera'
  ));

  const stopMotionAnalysis = useCallback(() => {
    motionControllerRef.current?.stop();
    motionControllerRef.current = null;
  }, []);

  const startMotionAnalysis = useCallback(() => {
    if (!liveMotionSessionId || !videoRef.current || !streamRef.current) {
      return;
    }
    stopMotionAnalysis();
    const controller = createLivePoseWindowController({
      video: videoRef.current,
      liveSessionId: liveMotionSessionId,
      adapter: createBrowserMediaPipePoseAdapter(),
      appendMotionWindow: async (summary, receivedAtMs) => {
        const response = await appendMotionWindow({
          apiUrl,
          summary,
          receivedAtMs,
        });
        if (liveMotionSessionId) {
          onMotionWindowAppended?.({
            liveSessionId: liveMotionSessionId,
            response,
            summary,
          });
        }
      },
      metadata: {
        workspace_id: workspaceId,
        source_session_id: session.session_id,
        source_types: session.source_types,
      },
      onStatus: setMotionStatus,
    });
    motionControllerRef.current = controller;
    controller.start();
  }, [
    apiUrl,
    liveMotionSessionId,
    onMotionWindowAppended,
    session.session_id,
    session.source_types,
    stopMotionAnalysis,
    workspaceId,
  ]);

  useEffect(() => {
    startMotionAnalysisRef.current = startMotionAnalysis;
  }, [startMotionAnalysis]);

  useEffect(() => {
    if (!liveMotionSessionId) {
      stopMotionAnalysis();
      setMotionStatus({ state: 'idle', appendedWindowCount: 0 });
      return undefined;
    }
    startMotionAnalysis();
    return () => stopMotionAnalysis();
  }, [liveMotionSessionId, startMotionAnalysis, stopMotionAnalysis]);

  useEffect(() => {
    if (!supportsCamera) {
      return undefined;
    }
    handleRef.current?.stop();
    stopMotionAnalysis();
    streamRef.current = null;
    setError(null);
    setReceiverNotice(null);
    setHasRemoteStream(false);
    setVideoFrameReady(false);
    const handle = startWorkspaceReceiverSession({
      apiBase: apiUrl,
      workspaceId,
      deviceSessionId: session.session_id,
      mediaSessionId: session.session_id,
      onRemoteStream: (stream) => {
        streamRef.current = stream;
        setHasRemoteStream(true);
        setVideoFrameReady(false);
        setReceiverNotice(null);
        setError(null);
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          try {
            const playResult = videoRef.current.play?.();
            if (playResult && typeof playResult.catch === 'function') {
              playResult.catch(() => {
                setReceiverNotice('Video track connected; tap reconnect if frames do not appear.');
              });
            }
          } catch {
            setReceiverNotice('Video track connected; tap reconnect if frames do not appear.');
          }
        }
        startMotionAnalysisRef.current();
      },
      onState: setState,
      onError: (nextError) => {
        setError(nextError.message);
        setReceiverNotice(null);
        setState('error');
      },
    });
    handleRef.current = handle;
    return () => {
      handle.stop();
      stopMotionAnalysis();
      streamRef.current = null;
      if (handleRef.current === handle) {
        handleRef.current = null;
      }
    };
  }, [apiUrl, receiverAttempt, session.session_id, stopMotionAnalysis, supportsCamera, workspaceId]);

  useEffect(() => {
    if (
      !supportsCamera ||
      hasRemoteStream ||
      state === 'idle' ||
      state === 'closed' ||
      state === 'error'
    ) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      setReceiverNotice('Receiver connected; waiting for the phone video track.');
    }, 8000);
    return () => window.clearTimeout(timer);
  }, [hasRemoteStream, receiverAttempt, state, supportsCamera]);

  useEffect(() => {
    if (!supportsCamera || !hasRemoteStream || videoFrameReady || error) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      setReceiverNotice('Video track connected; waiting for camera frames.');
    }, 3500);
    return () => window.clearTimeout(timer);
  }, [error, hasRemoteStream, supportsCamera, videoFrameReady]);

  if (!supportsCamera) {
    return null;
  }

  const waitingForFrames = hasRemoteStream && !videoFrameReady && !error;
  const receiverLabel = error
    || receiverNotice
    || (waitingForFrames ? 'video_track_waiting_for_frames' : state);
  const motionLabel = liveMotionSessionId
    ? `${motionStatus.state}${motionStatus.reason ? `: ${motionStatus.reason}` : ''} · windows ${motionStatus.appendedWindowCount}`
    : 'practice_required';
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
          {state === 'connected' || state === 'answer_sent' ? (
            <Video className="h-3 w-3 shrink-0" aria-hidden="true" />
          ) : (
            <VideoOff className="h-3 w-3 shrink-0" aria-hidden="true" />
          )}
          <span className="truncate">{receiverLabel}</span>
        </div>
        {(!hasRemoteStream && (receiverNotice || error)) || waitingForFrames ? (
          <div className="absolute inset-x-3 top-1/2 -translate-y-1/2 rounded-md bg-black/75 px-3 py-2 text-center text-xs font-medium text-white">
            <div>{receiverLabel}</div>
            <button
              type="button"
              className="mt-2 inline-flex items-center gap-1 rounded border border-white/30 px-2 py-1 text-[11px] font-semibold text-white hover:bg-white/10"
              onClick={() => setReceiverAttempt((current) => current + 1)}
            >
              <RefreshCw className="h-3 w-3" aria-hidden="true" />
              Reconnect receiver
            </button>
          </div>
        ) : null}
        <div
          className="absolute bottom-2 left-2 inline-flex max-w-[calc(100%-1rem)] items-center gap-1 rounded bg-black/70 px-2 py-1 text-[11px] font-medium text-white"
          data-testid={`phone-source-motion-status-${session.session_id}`}
        >
          <Activity className="h-3 w-3 shrink-0" aria-hidden="true" />
          <span className="truncate">{motionLabel}</span>
        </div>
      </div>
    </div>
  );
}

export default PhoneSourcePreview;
