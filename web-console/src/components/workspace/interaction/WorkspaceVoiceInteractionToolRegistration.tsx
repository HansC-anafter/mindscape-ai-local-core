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
  const { activeTarget } = useWorkspaceInteractionIngress();
  const toolLabel = t('workspaceVoiceToolLabel' as any);
  const contributions = React.useMemo(() => [{
    key: 'aol:voice',
    id: 'aol:voice',
    label: activeTarget
      ? toolLabel
      : `${toolLabel}: ${t('workspaceVoiceNoTarget' as any)}`,
    icon: <Mic className="h-4 w-4" aria-hidden="true" />,
    group: 'runtime' as const,
    order: 25,
    visible: true,
    disabled: !activeTarget,
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
  }], [activeTarget, apiUrl, t, toolLabel]);

  useWorkspaceGlobalToolContributions('workspace:voice-interaction', contributions);
  return null;
}
