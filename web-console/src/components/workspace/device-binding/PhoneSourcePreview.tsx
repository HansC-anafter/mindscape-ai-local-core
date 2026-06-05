'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Video, VideoOff } from 'lucide-react';

import type { DeviceSessionEntry } from '@/lib/device-binding/deviceBindingClient';
import {
  startWorkspaceReceiverSession,
  type WebRTCSessionHandle,
  type WebRTCSessionState,
} from '@/lib/media-transport/webrtcSessionClient';

interface PhoneSourcePreviewProps {
  apiUrl: string;
  workspaceId: string;
  session: DeviceSessionEntry;
}

export function PhoneSourcePreview({
  apiUrl,
  workspaceId,
  session,
}: PhoneSourcePreviewProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const handleRef = useRef<WebRTCSessionHandle | null>(null);
  const [state, setState] = useState<WebRTCSessionState | 'idle' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);
  const supportsCamera = session.source_types.some((sourceType) => (
    sourceType === 'phone_camera' ||
    sourceType === 'desktop_camera' ||
    sourceType === 'usb_camera' ||
    sourceType === 'virtual_camera'
  ));

  useEffect(() => {
    if (!supportsCamera) {
      return undefined;
    }
    handleRef.current?.stop();
    setError(null);
    const handle = startWorkspaceReceiverSession({
      apiBase: apiUrl,
      workspaceId,
      deviceSessionId: session.session_id,
      mediaSessionId: session.session_id,
      onRemoteStream: (stream) => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
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
      if (handleRef.current === handle) {
        handleRef.current = null;
      }
    };
  }, [apiUrl, session.session_id, supportsCamera, workspaceId]);

  if (!supportsCamera) {
    return null;
  }

  return (
    <div className="mt-2 overflow-hidden rounded-md border border-gray-200 bg-black dark:border-gray-700">
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
      </div>
    </div>
  );
}

export default PhoneSourcePreview;
