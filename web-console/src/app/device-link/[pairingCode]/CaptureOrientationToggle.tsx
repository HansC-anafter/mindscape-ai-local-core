'use client';

import React from 'react';
import { Loader2, RotateCw, Smartphone } from 'lucide-react';

import type { CaptureOrientation } from '@/lib/media-transport/webrtcSessionClient';

interface CaptureOrientationToggleProps {
  busy?: boolean;
  disabled?: boolean;
  orientation: CaptureOrientation;
  onToggle: () => void | Promise<void>;
}

export function CaptureOrientationToggle({
  busy = false,
  disabled = false,
  orientation,
  onToggle,
}: CaptureOrientationToggleProps) {
  const nextLabel = orientation === 'portrait' ? 'Use landscape capture' : 'Use portrait capture';
  const currentLabel = orientation === 'portrait' ? 'Portrait' : 'Landscape';
  return (
    <button
      type="button"
      onClick={() => void onToggle()}
      disabled={disabled || busy}
      className="inline-flex min-h-11 min-w-0 flex-col items-center justify-center gap-0.5 rounded-md border border-white/15 bg-white/10 px-2 py-2 text-xs font-semibold text-white transition-colors hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-50"
      aria-label={busy ? 'Switching capture orientation' : nextLabel}
      data-testid="capture-orientation-toggle"
    >
      <span className="inline-flex items-center gap-1">
        {busy ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
        ) : orientation === 'portrait' ? (
          <Smartphone className="h-3.5 w-3.5" aria-hidden="true" />
        ) : (
          <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
        )}
        {busy ? 'Switching' : 'Rotate'}
      </span>
      <span className="text-[10px] font-medium text-white/60">{currentLabel}</span>
    </button>
  );
}
