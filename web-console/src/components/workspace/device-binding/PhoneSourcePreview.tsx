'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Activity, Video, VideoOff } from 'lucide-react';

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
    const handle = startWorkspaceReceiverSession({
      apiBase: apiUrl,
      workspaceId,
      deviceSessionId: session.session_id,
      mediaSessionId: session.session_id,
      onRemoteStream: (stream) => {
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
        startMotionAnalysisRef.current();
      },
      onState: setState,
      onError: (nextError) => {
        setError(nextError.message);
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
  }, [apiUrl, session.session_id, stopMotionAnalysis, supportsCamera, workspaceId]);

  if (!supportsCamera) {
    return null;
  }

  const motionLabel = liveMotionSessionId
    ? `${motionStatus.state}${motionStatus.reason ? `: ${motionStatus.reason}` : ''} · windows ${motionStatus.appendedWindowCount}`
    : 'practice_required';

  return (
    <div
      className={cn(
        'mt-2 overflow-hidden rounded-md border border-gray-200 bg-black dark:border-gray-700',
        className,
      )}
    >
      <div className="relative aspect-video w-full">
        <video
          ref={videoRef}
          className="h-full w-full bg-black object-cover"
          autoPlay
          playsInline
          muted
          data-testid={`phone-source-preview-${session.session_id}`}
        />
        <div className="absolute left-2 top-2 inline-flex max-w-[calc(100%-1rem)] items-center gap-1 rounded bg-black/70 px-2 py-1 text-[11px] font-medium text-white">
          {state === 'connected' || state === 'answer_sent' ? (
            <Video className="h-3 w-3 shrink-0" aria-hidden="true" />
          ) : (
            <VideoOff className="h-3 w-3 shrink-0" aria-hidden="true" />
          )}
          <span className="truncate">{error || state}</span>
        </div>
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
