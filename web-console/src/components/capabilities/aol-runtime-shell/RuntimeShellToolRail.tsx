'use client';

import { useT } from '@/lib/i18n';
import type { AOLRuntimeShellState } from './AOLRuntimeShellContext';
import { RuntimeObjectSelectionAnchor } from './RuntimeObjectSelectionAnchor';
import { RuntimeFlowAnchor } from './RuntimeFlowAnchor';

interface RuntimeShellToolRailProps {
  state: AOLRuntimeShellState;
  canOpenFlow: boolean;
  onRequestObjectTargeting: () => void;
  onCancelObjectTargeting: () => void;
  onOpenFlow: () => void;
}

export function RuntimeShellToolRail({
  state,
  canOpenFlow,
  onRequestObjectTargeting,
  onCancelObjectTargeting,
  onOpenFlow,
}: RuntimeShellToolRailProps) {
  const t = useT();
  const objectLabel = state.mode === 'selecting'
    ? t('aolRuntimeShellCancelObjectSelection')
    : t('aolRuntimeShellSelectObject');
  const objectHelper = state.mode === 'meeting_opened'
    ? t('aolRuntimeShellSelectAnotherObject')
    : objectLabel;
  const flowLabel = state.mode === 'meeting_opened'
    ? t('aolRuntimeShellFlowOpen')
    : canOpenFlow
      ? t('aolRuntimeShellOpenFlow')
      : t('aolRuntimeShellFlowUnavailable');

  return (
    <nav
      className="pointer-events-auto flex h-full w-10 shrink-0 flex-col items-center border-l border-gray-200 bg-white/90 pb-3 pt-12 shadow-[-6px_0_18px_rgba(15,23,42,0.08)] backdrop-blur dark:border-gray-700 dark:bg-gray-900/90"
      data-testid="aol-shell-rail"
      aria-label={t('aolRuntimeShellTools')}
    >
      <div
        className="flex w-full flex-col items-center gap-1 border-b border-gray-200 px-1 pb-3 dark:border-gray-700"
        data-testid="aol-object-tool-group"
      >
        <RuntimeObjectSelectionAnchor
          state={state}
          onRequestObjectTargeting={onRequestObjectTargeting}
          onCancelObjectTargeting={onCancelObjectTargeting}
          label={objectLabel}
          helper={objectHelper}
        />
        <div className="text-center text-[6px] uppercase leading-none tracking-normal text-gray-400 dark:text-gray-500">
          {t('aolRuntimeShellSelect')}
        </div>
      </div>
      <div
        className="flex w-full flex-col items-center gap-1 px-1 pt-3"
        data-testid="aol-runtime-flow-tool-group"
      >
        <RuntimeFlowAnchor
          state={state}
          canOpenFlow={canOpenFlow}
          label={flowLabel}
          onOpenFlow={onOpenFlow}
        />
        <div className="text-center text-[6px] uppercase leading-none tracking-normal text-gray-400 dark:text-gray-500">
          {t('aolRuntimeShellFlow')}
        </div>
      </div>
    </nav>
  );
}

export default RuntimeShellToolRail;
