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
  return (
    <button
      type="button"
      onClick={() => void onToggle()}
      disabled={disabled || busy}
      className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-white/15 bg-white/10 px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-50"
      aria-label={busy ? 'Switching capture orientation' : nextLabel}
      data-testid="capture-orientation-toggle"
    >
      {busy ? (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      ) : orientation === 'portrait' ? (
        <Smartphone className="h-4 w-4" aria-hidden="true" />
      ) : (
        <RotateCw className="h-4 w-4" aria-hidden="true" />
      )}
      {busy ? 'Switching' : orientation === 'portrait' ? 'Portrait' : 'Landscape'}
    </button>
  );
}
