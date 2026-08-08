'use client';

import React from 'react';
import { Mic } from 'lucide-react';

import { useWorkspaceGlobalToolContributions } from '@/app/workspaces/[workspaceId]/components/useWorkspaceGlobalToolRail';
import { useT } from '@/lib/i18n';
import { useWorkspaceInteractionIngress } from '@/lib/workspace-interaction/WorkspaceInteractionIngressProvider';

const WorkspaceVoiceInteractionPanel = React.lazy(async () => {
  const module = await import('./WorkspaceVoiceInteractionPanel');
  return { default: module.WorkspaceVoiceInteractionPanel };
});

export function WorkspaceVoiceInteractionToolRegistration({
  apiUrl,
}: {
  apiUrl: string;
}) {
  const t = useT();
  const { activeTarget, targets } = useWorkspaceInteractionIngress();
  const toolLabel = t('workspaceVoiceToolLabel' as any);
  const ambiguousTarget = !activeTarget && targets.length > 0;
  const contributions = React.useMemo(() => [{
    key: 'aol:voice',
    id: 'aol:voice',
    label: ambiguousTarget
      ? `${toolLabel}: ${t('workspaceVoiceNoTarget' as any)}`
      : toolLabel,
    icon: <Mic className="h-4 w-4" aria-hidden="true" />,
    group: 'runtime' as const,
    order: 25,
    visible: true,
    disabled: ambiguousTarget,
    testId: 'workspace-voice-tool',
    renderPanel: () => (
      <React.Suspense
        fallback={(
          <div
            className="p-4 text-xs text-slate-500 dark:text-slate-400"
            data-testid="workspace-voice-panel-loading"
          >
            {t('workspaceVoicePanelLoading' as any)}
          </div>
        )}
      >
        <WorkspaceVoiceInteractionPanel apiUrl={apiUrl} />
      </React.Suspense>
    ),
  }], [ambiguousTarget, apiUrl, t, toolLabel]);

  useWorkspaceGlobalToolContributions('workspace:voice-interaction', contributions);
  return null;
}
