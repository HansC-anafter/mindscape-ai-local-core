'use client';

import {
  Activity,
  GitGraph,
  Package,
  Settings as SettingsIcon,
  Smartphone,
} from 'lucide-react';

import type {
  WorkspaceRightRegionGroup,
} from '@/lib/workspace-right-region/workspace-right-region-contract';
import { openAppRouteInNewWindow } from '@/lib/navigation/openAppRouteInNewWindow';
import {
  MotionSourceRailPanel,
  WorkspacePackToolPanel,
  WorkspaceRunsPanel,
  WorkspaceSettingsToolPanel,
} from '@/components/workspace/workspaceCoreToolPanelLazyComponents';
import type { WorkspaceGlobalToolContribution } from '../../components/useWorkspaceGlobalToolRail';
import type { Translator } from '@/lib/i18n/contracts';

export const WORKSPACE_ACTIVE_PANEL_TOGGLE_BINDING_ID = 'tool_rail:workspace:active_panel:toggle';
export const WORKSPACE_TOOL_RAIL_COMMAND_ID = 'workspace.tool_rail.toggle';

export const GROUP_LABELS: Partial<Record<WorkspaceRightRegionGroup, string>> = {
  execution: 'workspaceToolGroupExecution',
  workspace: 'workspaceToolGroupWorkspace',
  graph: 'workspaceToolGroupGraph',
  capability: 'workspaceToolGroupPack',
  runtime: 'workspaceToolGroupRuntime',
  tool_runtime: 'workspaceToolGroupToolRuntime',
};

const GROUP_ORDER: Partial<Record<WorkspaceRightRegionGroup, number>> = {
  execution: 10,
  workspace: 20,
  graph: 30,
  capability: 50,
  runtime: 60,
  tool_runtime: 70,
};

export function isActiveExecutionStatus(status: unknown): boolean {
  const normalized = String(status || '').toLowerCase();
  return normalized === 'running' || normalized === 'queued' || normalized === 'pending' || normalized === 'paused';
}

export function groupOrder(group: WorkspaceRightRegionGroup): number {
  return GROUP_ORDER[group] ?? 100;
}

export function sortContributions(
  left: WorkspaceGlobalToolContribution,
  right: WorkspaceGlobalToolContribution,
): number {
  return groupOrder(left.group) - groupOrder(right.group)
    || left.order - right.order
    || left.key.localeCompare(right.key);
}

export function resolveVisibleContributions(
  coreContributions: WorkspaceGlobalToolContribution[],
  registeredScopeContributions: Record<string, WorkspaceGlobalToolContribution[]>,
): WorkspaceGlobalToolContribution[] {
  const contributionMap = new Map<string, WorkspaceGlobalToolContribution>();
  [...coreContributions, ...Object.values(registeredScopeContributions).flat()]
    .filter((contribution) => contribution.visible !== false)
    .forEach((contribution) => {
      if (!contributionMap.has(contribution.key)) {
        contributionMap.set(contribution.key, contribution);
      }
    });
  return [...contributionMap.values()].sort(sortContributions);
}

export function bindingIdForContribution(contribution: WorkspaceGlobalToolContribution): string {
  return `workspace_tool:${contribution.key}:open`;
}

export function shortcutOwnerForContribution(contribution: WorkspaceGlobalToolContribution) {
  if (
    contribution.key.startsWith('core:')
    || contribution.key.startsWith('aol:')
    || contribution.key.startsWith('workspace-surface:')
  ) {
    return {
      ownerType: 'core' as const,
      ownerId: contribution.key.startsWith('aol:') ? 'runtime' : 'workspace',
      ownerLabel: contribution.key.startsWith('aol:') ? 'Runtime' : 'Workspace',
    };
  }

  const ownerId = contribution.key.split(':')[0] || 'pack';
  return {
    ownerType: 'pack' as const,
    ownerId,
    ownerLabel: ownerId,
  };
}

export function buildCoreWorkspaceToolContributions({
  workspaceId,
  apiUrl,
  activeCapabilityCode,
  activeExecutionCount,
  remoteSurfaceMode = false,
  t,
}: {
  workspaceId: string;
  apiUrl: string;
  activeCapabilityCode: string | null;
  activeExecutionCount: number;
  remoteSurfaceMode?: boolean;
  t: Translator;
}): WorkspaceGlobalToolContribution[] {
  const contributions: WorkspaceGlobalToolContribution[] = [
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
  ];
  return remoteSurfaceMode
    ? contributions.filter((item) => !['core:settings', 'core:graph'].includes(item.key))
    : contributions;
}
