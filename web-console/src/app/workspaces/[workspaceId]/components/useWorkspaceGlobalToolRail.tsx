'use client';

import React from 'react';

import type { WorkspaceToolRailGroup } from '@/components/workspace/WorkspaceToolRail';
import type {
  WorkspaceRightRegionCoreContributionId,
  WorkspaceRightRegionGroup,
} from '@/lib/workspace-right-region/workspace-right-region-contract';

export interface WorkspaceGlobalToolContribution {
  key: string;
  id?: WorkspaceRightRegionCoreContributionId | string;
  label: string;
  icon?: React.ReactNode;
  group: WorkspaceRightRegionGroup;
  order: number;
  defaultShortcut?: string;
  testId?: string;
  badge?: number | string | null;
  visible?: boolean;
  disabled?: boolean;
  renderPanel?: () => React.ReactNode;
  renderRailButton?: () => React.ReactNode;
  onSelect?: () => void;
}

export interface WorkspaceGlobalToolRailContextValue {
  activeToolKey: string | null;
  setActiveToolKey: React.Dispatch<React.SetStateAction<string | null>>;
  activeCapabilityCode: string | null;
  setActiveCapabilityCode: React.Dispatch<React.SetStateAction<string | null>>;
  registerToolContributions: (
    scopeId: string,
    contributions: WorkspaceGlobalToolContribution[],
  ) => () => void;
}

export interface WorkspaceGlobalToolRailResolvedGroup extends WorkspaceToolRailGroup {
  order: number;
}

export const WorkspaceGlobalToolRailContext = React.createContext<WorkspaceGlobalToolRailContextValue | null>(null);

export function useWorkspaceGlobalToolRail(): WorkspaceGlobalToolRailContextValue {
  const value = React.useContext(WorkspaceGlobalToolRailContext);
  if (!value) {
    throw new Error('useWorkspaceGlobalToolRail must be used inside WorkspaceGlobalToolRailProvider');
  }
  return value;
}

export function useOptionalWorkspaceGlobalToolRail(): WorkspaceGlobalToolRailContextValue | null {
  return React.useContext(WorkspaceGlobalToolRailContext);
}

export function useWorkspaceGlobalToolContributions(
  scopeId: string,
  contributions: WorkspaceGlobalToolContribution[],
) {
  const rail = useOptionalWorkspaceGlobalToolRail();
  const registerToolContributions = rail?.registerToolContributions;

  React.useEffect(() => {
    if (!registerToolContributions) {
      return undefined;
    }
    return registerToolContributions(scopeId, contributions);
  }, [registerToolContributions, scopeId, contributions]);
}
