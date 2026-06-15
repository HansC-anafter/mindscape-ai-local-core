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
  return (
    <button
      type="button"
      onClick={() => void onFlip()}
      disabled={disabled || busy}
      className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-white/15 bg-white/10 px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-50"
      aria-label={busy ? 'Switching camera' : nextLabel}
      data-testid="camera-facing-mode-toggle"
    >
      {busy ? (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      ) : facingMode === 'environment' ? (
        <Smartphone className="h-4 w-4" aria-hidden="true" />
      ) : (
        <RotateCcw className="h-4 w-4" aria-hidden="true" />
      )}
      {busy ? 'Switching' : facingMode === 'environment' ? 'Rear' : 'Front'}
    </button>
  );
}
