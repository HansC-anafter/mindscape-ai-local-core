import React from 'react';
import { Activity, GitGraph, Package, Settings as SettingsIcon, Smartphone } from 'lucide-react';

import { openAppRouteInNewWindow } from '@/lib/navigation/openAppRouteInNewWindow';
import { useT } from '@/lib/i18n';
import type { WorkspaceGlobalToolContribution } from './useWorkspaceGlobalToolRail';

const WorkspaceRunsPanel = React.lazy(() => import('../capability-ui-hosts/WorkspaceRunsPanel'));
const WorkspaceSettingsToolPanel = React.lazy(() => import('../capability-ui-hosts/WorkspaceSettingsToolPanel'));
const WorkspacePackToolPanel = React.lazy(() => import('../capability-ui-hosts/WorkspacePackToolPanel'));
const MotionSourceRailPanel = React.lazy(() => import('@/components/workspace/device-binding/MotionSourceRailPanel'));

interface WorkspaceCoreToolContributionsOptions {
  activeCapabilityCode: string | null;
  activeExecutionCount: number;
  apiUrl: string;
  workspaceId: string;
}

export function WorkspaceToolPanelLoadingState({ label }: { label: string }) {
  const t = useT();
  return (
    <div className="flex h-full items-center justify-center p-3 text-xs text-gray-500 dark:text-gray-400">
      {t('workspaceToolPanelLoading', { label })}
    </div>
  );
}

export function useWorkspaceCoreToolContributions({
  activeCapabilityCode,
  activeExecutionCount,
  apiUrl,
  workspaceId,
}: WorkspaceCoreToolContributionsOptions): WorkspaceGlobalToolContribution[] {
  const t = useT();
  return React.useMemo<WorkspaceGlobalToolContribution[]>(() => ([
    {
      key: 'core:runs_panel',
      id: 'runs_panel',
      label: t('workspaceToolRuns'),
      icon: <Activity aria-hidden="true" className="h-4 w-4" />,
      group: 'execution',
      order: 10,
      defaultShortcut: 'R',
      badge: activeExecutionCount || null,
      testId: 'workspace-runs-tool',
      renderPanel: () => (
        <WorkspaceRunsPanel
          workspaceId={workspaceId}
          activeCapabilityCode={activeCapabilityCode}
        />
      ),
    },
    {
      key: 'core:settings',
      id: 'settings',
      label: t('workspaceToolSettings'),
      icon: <SettingsIcon aria-hidden="true" className="h-4 w-4" />,
      group: 'workspace',
      order: 20,
      defaultShortcut: 'S',
      testId: 'workspace-settings-tool',
      renderPanel: () => (
        <WorkspaceSettingsToolPanel workspaceId={workspaceId} apiUrl={apiUrl} />
      ),
    },
    {
      key: 'core:pack',
      id: 'pack',
      label: t('workspaceToolPack'),
      icon: <Package aria-hidden="true" className="h-4 w-4" />,
      group: 'capability',
      order: 30,
      defaultShortcut: 'A',
      testId: 'workspace-pack-tool',
      renderPanel: () => (
        <WorkspacePackToolPanel workspaceId={workspaceId} apiUrl={apiUrl} />
      ),
    },
    {
      key: 'core:motion_source',
      id: 'motion_source',
      label: t('workspaceToolMotionSource'),
      icon: <Smartphone aria-hidden="true" className="h-4 w-4" />,
      group: 'runtime',
      order: 30,
      defaultShortcut: 'C',
      testId: 'workspace-motion-source-tool',
      renderPanel: () => (
        <MotionSourceRailPanel workspaceId={workspaceId} apiUrl={apiUrl} />
      ),
    },
    {
      key: 'core:graph',
      id: 'graph',
      label: t('workspaceToolGraph'),
      icon: <GitGraph aria-hidden="true" className="h-4 w-4" />,
      group: 'graph',
      order: 40,
      defaultShortcut: 'G',
      testId: 'workspace-graph-tool',
      onSelect: () => {
        openAppRouteInNewWindow(`/mindscape/canvas?workspaceId=${encodeURIComponent(workspaceId)}`);
      },
    },
  ]), [activeCapabilityCode, activeExecutionCount, apiUrl, t, workspaceId]);
}
