'use client';

import React from 'react';
import { Loader2, Maximize2, Minimize2 } from 'lucide-react';

interface CaptureFullscreenButtonProps {
  busy?: boolean;
  disabled?: boolean;
  isFullscreen: boolean;
  onToggle: () => void | Promise<void>;
}

export function CaptureFullscreenButton({
  busy = false,
  disabled = false,
  isFullscreen,
  onToggle,
}: CaptureFullscreenButtonProps) {
  return (
    <button
      type="button"
      onClick={() => void onToggle()}
      disabled={disabled || busy}
      className="inline-flex min-h-11 min-w-0 flex-col items-center justify-center gap-0.5 rounded-md border border-white/15 bg-white/10 px-2 py-2 text-xs font-semibold text-white transition-colors hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-50"
      aria-label={busy ? 'Switching fullscreen' : isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
      data-testid="capture-fullscreen-button"
    >
      <span className="inline-flex items-center gap-1">
        {busy ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
        ) : isFullscreen ? (
          <Minimize2 className="h-3.5 w-3.5" aria-hidden="true" />
        ) : (
          <Maximize2 className="h-3.5 w-3.5" aria-hidden="true" />
        )}
        {busy ? 'Opening' : isFullscreen ? 'Exit' : 'Full'}
      </span>
      <span className="text-[10px] font-medium text-white/60">screen</span>
    </button>
  );
}
