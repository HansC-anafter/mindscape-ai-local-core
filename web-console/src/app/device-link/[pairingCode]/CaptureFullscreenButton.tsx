'use client';

import React from 'react';
import { Maximize2, Minimize2 } from 'lucide-react';

interface CaptureFullscreenButtonProps {
  disabled?: boolean;
  isFullscreen: boolean;
  onToggle: () => void | Promise<void>;
}

export function CaptureFullscreenButton({
  disabled = false,
  isFullscreen,
  onToggle,
}: CaptureFullscreenButtonProps) {
  return (
    <button
      type="button"
      onClick={() => void onToggle()}
      disabled={disabled}
      className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-white/15 bg-white/10 px-3 py-2 text-sm font-semibold text-white transition-colors hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-50"
      aria-label={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
      data-testid="capture-fullscreen-button"
    >
      {isFullscreen ? (
        <Minimize2 className="h-4 w-4" aria-hidden="true" />
      ) : (
        <Maximize2 className="h-4 w-4" aria-hidden="true" />
      )}
      {isFullscreen ? 'Exit' : 'Fullscreen'}
    </button>
  );
}
