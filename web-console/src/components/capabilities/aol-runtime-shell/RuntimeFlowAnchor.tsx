'use client';

import { GitBranch } from 'lucide-react';

import type { AOLRuntimeShellState } from './AOLRuntimeShellContext';

interface RuntimeFlowAnchorProps {
  state: AOLRuntimeShellState;
  canOpenFlow: boolean;
  label: string;
  onOpenFlow: () => void;
}

export function RuntimeFlowAnchor({
  state,
  canOpenFlow,
  label,
  onOpenFlow,
}: RuntimeFlowAnchorProps) {
  const isOpen = state.mode === 'meeting_opened';
  const isBusy = state.mode === 'attaching';
  const isDisabled = !canOpenFlow || isBusy;

  return (
    <button
      type="button"
      onClick={onOpenFlow}
      disabled={isDisabled}
      className={`inline-flex h-6 w-6 items-center justify-center rounded-md border text-[9px] font-semibold shadow-sm backdrop-blur transition-colors ${
        isOpen
          ? 'border-blue-200 bg-blue-600 text-white hover:bg-blue-700 dark:border-blue-500/40 dark:bg-blue-500 dark:hover:bg-blue-400'
          : isDisabled
            ? 'cursor-not-allowed border-gray-200 bg-gray-100/80 text-gray-400 shadow-none dark:border-gray-800 dark:bg-gray-900/70 dark:text-gray-600'
            : 'border-gray-200 bg-white/95 text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900/95 dark:text-gray-100 dark:hover:bg-gray-800'
      }`}
      data-testid="aol-runtime-flow-anchor"
      aria-pressed={isOpen}
      aria-label={label}
      title={label}
    >
      <GitBranch className="h-3 w-3" aria-hidden="true" />
    </button>
  );
}

export default RuntimeFlowAnchor;
