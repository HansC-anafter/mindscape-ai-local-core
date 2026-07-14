import type { WorkspaceRightRegionGroup } from '@/lib/workspace-right-region/workspace-right-region-contract';
import type { WorkspaceGlobalToolContribution } from './useWorkspaceGlobalToolRail';

export const WORKSPACE_ACTIVE_PANEL_TOGGLE_BINDING_ID = 'tool_rail:workspace:active_panel:toggle';
export const WORKSPACE_TOOL_RAIL_COMMAND_ID = 'workspace.tool_rail.toggle';

export const GROUP_LABELS: Record<WorkspaceRightRegionGroup, string> = {
  execution: 'Runs',
  workspace: 'Workspace',
  meeting: 'Meeting',
  graph: 'Graph',
  capability: 'Pack',
  runtime: 'Runtime',
  tool_runtime: 'Tool Runtime',
  data: 'Data',
};

export const GROUP_ORDER: Record<WorkspaceRightRegionGroup, number> = {
  execution: 10,
  workspace: 20,
  graph: 30,
  meeting: 40,
  capability: 50,
  runtime: 60,
  tool_runtime: 70,
  data: 80,
};

export function isActiveExecutionStatus(status: unknown): boolean {
  const normalized = String(status || '').toLowerCase();
  return normalized === 'running' || normalized === 'queued' || normalized === 'pending' || normalized === 'paused';
}

export function sortContributions(
  left: WorkspaceGlobalToolContribution,
  right: WorkspaceGlobalToolContribution,
): number {
  return left.order - right.order || left.key.localeCompare(right.key);
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
  return [...contributionMap.values()].sort((left, right) => {
    const groupCompare = GROUP_ORDER[left.group] - GROUP_ORDER[right.group];
    return groupCompare || sortContributions(left, right);
  });
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
