'use client';

import { MousePointer2 } from 'lucide-react';

import type { AOLRuntimeShellState } from './AOLRuntimeShellContext';

interface RuntimeObjectSelectionAnchorProps {
  state: AOLRuntimeShellState;
  onRequestObjectTargeting: () => void;
  onCancelObjectTargeting: () => void;
  label: string;
  helper: string;
  tone?: 'light' | 'dark';
}

export function RuntimeObjectSelectionAnchor({
  state,
  onRequestObjectTargeting,
  onCancelObjectTargeting,
  label,
  helper,
  tone = 'light',
}: RuntimeObjectSelectionAnchorProps) {
  const isActive = state.mode !== 'idle' && state.mode !== 'meeting_opened';
  const activeClassName = tone === 'dark'
    ? 'border-amber-400 bg-amber-400 text-stone-950 hover:bg-amber-300'
    : 'border-blue-200 bg-blue-600 text-white hover:bg-blue-700 dark:border-blue-500/40 dark:bg-blue-500 dark:hover:bg-blue-400';
  const inactiveClassName = tone === 'dark'
    ? 'border-stone-700 bg-stone-950/95 text-stone-200 hover:bg-stone-900'
    : 'border-gray-200 bg-white/95 text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900/95 dark:text-gray-100 dark:hover:bg-gray-800';

  return (
    <button
      type="button"
      onClick={state.mode === 'selecting' ? onCancelObjectTargeting : onRequestObjectTargeting}
      className={`inline-flex h-6 w-6 flex-col items-center justify-center rounded-md border text-[9px] font-semibold shadow-sm backdrop-blur transition-colors ${
        isActive ? activeClassName : inactiveClassName
      }`}
      data-testid="aol-global-anchor"
      aria-pressed={isActive}
      title={helper}
      aria-label={label}
    >
      <MousePointer2 className="h-3 w-3" aria-hidden="true" />
    </button>
  );
}

export default RuntimeObjectSelectionAnchor;
