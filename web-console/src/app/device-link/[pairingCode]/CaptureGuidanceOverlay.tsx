'use client';

import React from 'react';
import { Activity, CheckCircle2, SunMedium, VideoOff } from 'lucide-react';

import type { WebRTCSessionState } from '@/lib/media-transport/webrtcSessionClient';
import type { LinkState, SourceMode } from './useDeviceLinkCaptureSession';

interface CaptureGuidanceOverlayProps {
  linkState: LinkState;
  mediaState: WebRTCSessionState | 'idle' | 'error';
  sourceMode: SourceMode;
  hasStream: boolean;
}

function guidanceCopy({
  linkState,
  mediaState,
  sourceMode,
  hasStream,
}: CaptureGuidanceOverlayProps) {
  if (linkState === 'secure_context_required') {
    return {
      tone: 'warn',
      title: 'HTTPS required',
      body: 'Open the QR link from the LAN HTTPS origin before starting capture.',
      icon: VideoOff,
    };
  }
  if (linkState === 'error') {
    return {
      tone: 'warn',
      title: 'Capture needs attention',
      body: 'Check camera permission, network, and pairing code before reconnecting.',
      icon: VideoOff,
    };
  }
  if (!hasStream || mediaState === 'idle') {
    return {
      tone: 'idle',
      title: 'Frame your full body',
      body: sourceMode === 'phone'
        ? 'Place the phone far enough to keep head, hands, hips, knees, and feet in frame.'
        : 'Select a camera source and keep the practice area fully visible.',
      icon: Activity,
    };
  }
  if (mediaState === 'connected' || linkState === 'streaming') {
    return {
      tone: 'ready',
      title: 'Capture ready',
      body: 'Keep the center line stable and avoid cutting off head or feet during movement.',
      icon: CheckCircle2,
    };
  }
  return {
    tone: 'active',
    title: 'Hold position',
    body: 'Keep lighting even and leave space around the full body while the stream connects.',
    icon: SunMedium,
  };
}

export function CaptureGuidanceOverlay(props: CaptureGuidanceOverlayProps) {
  const copy = guidanceCopy(props);
  const Icon = copy.icon;
  const toneClass = copy.tone === 'ready'
    ? 'border-emerald-300/30 bg-emerald-500/15 text-emerald-50'
    : copy.tone === 'warn'
      ? 'border-amber-300/30 bg-amber-500/20 text-amber-50'
      : 'border-white/15 bg-black/40 text-white';

  return (
    <div className="pointer-events-none absolute inset-0" data-testid="capture-guidance-overlay">
      <div className="absolute inset-x-[17%] top-[8%] h-[84%] rounded-[999px] border border-white/35" />
      <div className="absolute left-1/2 top-[9%] h-[82%] -translate-x-1/2 border-l border-dashed border-white/35" />
      <div className="absolute inset-x-4 bottom-4">
        <div className={`flex items-start gap-3 rounded-md border px-3 py-2 shadow-lg backdrop-blur ${toneClass}`}>
          <Icon className="mt-0.5 h-4 w-4 flex-none" aria-hidden="true" />
          <div>
            <div className="text-sm font-semibold">{copy.title}</div>
            <div className="text-xs leading-5 opacity-90">{copy.body}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
