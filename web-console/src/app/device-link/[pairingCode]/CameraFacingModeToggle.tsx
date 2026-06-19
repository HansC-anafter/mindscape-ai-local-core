'use client';

import React from 'react';
import { Loader2, RotateCcw, Smartphone } from 'lucide-react';

import type { CameraFacingMode } from '@/lib/media-transport/webrtcSessionClient';

interface CameraFacingModeToggleProps {
  busy?: boolean;
  disabled?: boolean;
  facingMode: CameraFacingMode;
  onFlip: () => void | Promise<void>;
}

export function CameraFacingModeToggle({
  busy = false,
  disabled = false,
  facingMode,
  onFlip,
}: CameraFacingModeToggleProps) {
  const nextLabel = facingMode === 'environment' ? 'Use front camera' : 'Use rear camera';
  const currentLabel = facingMode === 'environment' ? 'Rear' : 'Front';
  return (
    <button
      type="button"
      onClick={() => void onFlip()}
      disabled={disabled || busy}
      className="inline-flex min-h-11 min-w-0 flex-col items-center justify-center gap-0.5 rounded-md border border-white/15 bg-white/10 px-2 py-2 text-xs font-semibold text-white transition-colors hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-50"
      aria-label={busy ? 'Switching camera' : nextLabel}
      data-testid="camera-facing-mode-toggle"
    >
      <span className="inline-flex items-center gap-1">
        {busy ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
        ) : facingMode === 'environment' ? (
          <Smartphone className="h-3.5 w-3.5" aria-hidden="true" />
        ) : (
          <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
        )}
        {busy ? 'Switching' : 'Flip'}
      </span>
      <span className="text-[10px] font-medium text-white/60">{currentLabel}</span>
    </button>
  );
}
