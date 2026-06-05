'use client';

import React, { useEffect, useRef } from 'react';
import { MonitorUp, VideoOff } from 'lucide-react';

import { sourceKindLabel, type CameraSourceKind } from '@/lib/media-transport/mediaDeviceCatalog';
import type { WebRTCSessionState } from '@/lib/media-transport/webrtcSessionClient';

interface DesktopSourcePreviewProps {
  stream: MediaStream | null;
  sourceKind: CameraSourceKind;
  state: WebRTCSessionState | 'idle' | 'error';
  error?: string | null;
}

export function DesktopSourcePreview({
  stream,
  sourceKind,
  state,
  error = null,
}: DesktopSourcePreviewProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.srcObject = stream;
    }
  }, [stream]);

  return (
    <div className="mb-5 overflow-hidden rounded-md border border-gray-800 bg-black">
      <div className="relative aspect-video w-full">
        <video
          ref={videoRef}
          className="h-full w-full bg-black object-cover"
          autoPlay
          playsInline
          muted
          data-testid="desktop-source-local-preview"
        />
        <div className="absolute left-2 top-2 inline-flex max-w-[calc(100%-1rem)] items-center gap-1 rounded bg-black/70 px-2 py-1 text-[11px] font-medium text-white">
          {state === 'connected' || state === 'offer_sent' || state === 'answer_received' ? (
            <MonitorUp className="h-3 w-3 shrink-0" aria-hidden="true" />
          ) : (
            <VideoOff className="h-3 w-3 shrink-0" aria-hidden="true" />
          )}
          <span className="truncate">
            {sourceKindLabel(sourceKind)} - {error || state}
          </span>
        </div>
      </div>
    </div>
  );
}

export default DesktopSourcePreview;
