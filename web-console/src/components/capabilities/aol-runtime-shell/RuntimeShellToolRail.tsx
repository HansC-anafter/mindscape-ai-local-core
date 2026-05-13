'use client';

import { useT } from '@/lib/i18n';
import {
  WorkspaceToolRail,
  type WorkspaceToolRailGroup,
} from '@/components/workspace/WorkspaceToolRail';
import type { AOLRuntimeShellState } from './AOLRuntimeShellContext';
import { RuntimeObjectSelectionAnchor } from './RuntimeObjectSelectionAnchor';
import { RuntimeFlowAnchor } from './RuntimeFlowAnchor';

interface RuntimeShellToolRailProps {
  state: AOLRuntimeShellState;
  canOpenFlow: boolean;
  onRequestObjectTargeting: () => void;
  onCancelObjectTargeting: () => void;
  onOpenFlow: () => void;
  extraGroups?: WorkspaceToolRailGroup[];
}

function resolveRuntimeShellToolRailTone(): 'light' | 'dark' {
  return 'light';
}

export function RuntimeShellToolRail({
  state,
  canOpenFlow,
  onRequestObjectTargeting,
  onCancelObjectTargeting,
  onOpenFlow,
  extraGroups = [],
}: RuntimeShellToolRailProps) {
  const t = useT();
  const tone = resolveRuntimeShellToolRailTone();
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
    <WorkspaceToolRail
      ariaLabel={t('aolRuntimeShellTools')}
      tone={tone}
      testId="aol-shell-rail"
      groups={[
        {
          id: 'object',
          label: t('aolRuntimeShellSelect'),
          testId: 'aol-object-tool-group',
          children: (
            <RuntimeObjectSelectionAnchor
              state={state}
              onRequestObjectTargeting={onRequestObjectTargeting}
              onCancelObjectTargeting={onCancelObjectTargeting}
              label={objectLabel}
              helper={objectHelper}
              tone={tone}
            />
          ),
        },
        {
          id: 'flow',
          label: t('aolRuntimeShellFlow'),
          testId: 'aol-runtime-flow-tool-group',
          children: (
            <RuntimeFlowAnchor
              state={state}
              canOpenFlow={canOpenFlow}
              label={flowLabel}
              onOpenFlow={onOpenFlow}
              tone={tone}
            />
          ),
        },
        ...extraGroups,
      ]}
    />
  );
}

export default RuntimeShellToolRail;
