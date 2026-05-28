'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { Activity, GitGraph, Package, Settings as SettingsIcon, X } from 'lucide-react';

import {
  WorkspaceToolRail,
  WorkspaceToolRailButton,
  type WorkspaceToolRailGroup,
} from '@/components/workspace/WorkspaceToolRail';
import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { getApiBaseUrl } from '@/lib/api-url';
import {
  WORKSPACE_RIGHT_REGION_PANEL_BODY_CLASS,
  WORKSPACE_RIGHT_REGION_PANEL_WIDTH_CLASS,
  type WorkspaceRightRegionGroup,
} from '@/lib/workspace-right-region/workspace-right-region-contract';
import {
  WorkspaceGlobalToolRailContext,
  type WorkspaceGlobalToolContribution,
} from './useWorkspaceGlobalToolRail';

const WorkspaceRunsPanel = React.lazy(() => import('../capability-ui-hosts/WorkspaceRunsPanel'));
const WorkspaceSettingsToolPanel = React.lazy(() => import('../capability-ui-hosts/WorkspaceSettingsToolPanel'));
const WorkspacePackToolPanel = React.lazy(() => import('../capability-ui-hosts/WorkspacePackToolPanel'));

const GROUP_LABELS: Record<WorkspaceRightRegionGroup, string> = {
  execution: 'Runs',
  workspace: 'Workspace',
  meeting: 'Meeting',
  capability: 'Pack',
  runtime: 'Runtime',
  tool_runtime: 'Tool Runtime',
  data: 'Data',
};

const GROUP_ORDER: Record<WorkspaceRightRegionGroup, number> = {
  execution: 10,
  workspace: 20,
  meeting: 30,
  capability: 40,
  runtime: 50,
  tool_runtime: 60,
  data: 70,
};

function isActiveExecutionStatus(status: unknown): boolean {
  const normalized = String(status || '').toLowerCase();
  return normalized === 'running' || normalized === 'queued' || normalized === 'pending' || normalized === 'paused';
}

function WorkspaceToolPanelLoadingState({ label }: { label: string }) {
  return (
    <div className="flex h-full items-center justify-center p-3 text-xs text-gray-500 dark:text-gray-400">
      Loading {label}...
    </div>
  );
}

function sortContributions(
  left: WorkspaceGlobalToolContribution,
  right: WorkspaceGlobalToolContribution,
): number {
  return left.order - right.order || left.key.localeCompare(right.key);
}

function resolveVisibleContributions(
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

interface WorkspaceGlobalToolRailProviderProps {
  workspaceId: string;
  children: React.ReactNode;
}

export default function WorkspaceGlobalToolRailProvider({
  workspaceId,
  children,
}: WorkspaceGlobalToolRailProviderProps) {
  const router = useRouter();
  const apiUrl = getApiBaseUrl();
  const workspaceData = useWorkspaceDataOptional();
  const [activeToolKey, setActiveToolKey] = React.useState<string | null>(null);
  const [activeCapabilityCode, setActiveCapabilityCode] = React.useState<string | null>(null);
  const [registeredScopeContributions, setRegisteredScopeContributions] = React.useState<Record<string, WorkspaceGlobalToolContribution[]>>({});
  const activeExecutionCount = (workspaceData?.executions || []).filter((execution) => (
    isActiveExecutionStatus(execution.status)
  )).length;

  const registerToolContributions = React.useCallback((
    scopeId: string,
    contributions: WorkspaceGlobalToolContribution[],
  ) => {
    setRegisteredScopeContributions((current) => ({
      ...current,
      [scopeId]: contributions,
    }));
    return () => {
      setRegisteredScopeContributions((current) => {
        if (!Object.prototype.hasOwnProperty.call(current, scopeId)) {
          return current;
        }
        const next = { ...current };
        delete next[scopeId];
        return next;
      });
    };
  }, []);

  const coreContributions = React.useMemo<WorkspaceGlobalToolContribution[]>(() => [
    {
      key: 'core:runs_panel',
      id: 'runs_panel',
      label: 'Runs',
      icon: <Activity aria-hidden="true" className="h-4 w-4" />,
      group: 'execution',
      order: 10,
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
      label: 'Settings',
      icon: <SettingsIcon aria-hidden="true" className="h-4 w-4" />,
      group: 'workspace',
      order: 20,
      testId: 'workspace-settings-tool',
      renderPanel: () => (
        <WorkspaceSettingsToolPanel workspaceId={workspaceId} apiUrl={apiUrl} />
      ),
    },
    {
      key: 'core:pack',
      id: 'pack',
      label: 'Pack',
      icon: <Package aria-hidden="true" className="h-4 w-4" />,
      group: 'capability',
      order: 30,
      testId: 'workspace-pack-tool',
      renderPanel: () => (
        <WorkspacePackToolPanel workspaceId={workspaceId} apiUrl={apiUrl} />
      ),
    },
    {
      key: 'core:graph',
      id: 'graph',
      label: 'Graph',
      icon: <GitGraph aria-hidden="true" className="h-4 w-4" />,
      group: 'workspace',
      order: 40,
      testId: 'workspace-graph-tool',
      onSelect: () => {
        router.push(`/mindscape/canvas?workspaceId=${encodeURIComponent(workspaceId)}`);
      },
    },
  ], [activeCapabilityCode, activeExecutionCount, apiUrl, router, workspaceId]);

  const visibleContributions = React.useMemo(
    () => resolveVisibleContributions(coreContributions, registeredScopeContributions),
    [coreContributions, registeredScopeContributions],
  );
  const activeContribution = React.useMemo(
    () => visibleContributions.find((contribution) => contribution.key === activeToolKey) || null,
    [activeToolKey, visibleContributions],
  );

  React.useEffect(() => {
    if (activeToolKey && (!activeContribution || !activeContribution.renderPanel)) {
      setActiveToolKey(null);
    }
  }, [activeContribution, activeToolKey]);

  const groups = React.useMemo<WorkspaceToolRailGroup[]>(() => {
    const grouped = new Map<WorkspaceRightRegionGroup, WorkspaceGlobalToolContribution[]>();
    visibleContributions.forEach((contribution) => {
      const items = grouped.get(contribution.group) || [];
      items.push(contribution);
      grouped.set(contribution.group, items);
    });

    return [...grouped.entries()]
      .sort(([leftGroup], [rightGroup]) => GROUP_ORDER[leftGroup] - GROUP_ORDER[rightGroup])
      .map(([group, contributions]) => ({
        id: `workspace-global-${group}`,
        label: GROUP_LABELS[group],
        testId: `workspace-global-tool-group-${group}`,
        children: (
          <>
            {contributions.sort(sortContributions).map((contribution) => (
              <React.Fragment key={contribution.key}>
                {contribution.renderRailButton ? contribution.renderRailButton() : (
                  <WorkspaceToolRailButton
                    label={contribution.label}
                    icon={contribution.icon}
                    active={activeToolKey === contribution.key}
                    disabled={contribution.disabled}
                    badge={contribution.badge}
                    testId={contribution.testId}
                    onClick={() => {
                      if (contribution.disabled) {
                        return;
                      }
                      if (contribution.onSelect) {
                        setActiveToolKey(null);
                        contribution.onSelect();
                        return;
                      }
                      if (contribution.renderPanel) {
                        setActiveToolKey((current) => (current === contribution.key ? null : contribution.key));
                      }
                    }}
                  />
                )}
              </React.Fragment>
            ))}
          </>
        ),
      }));
  }, [activeToolKey, visibleContributions]);

  const contextValue = React.useMemo(() => ({
    activeToolKey,
    setActiveToolKey,
    activeCapabilityCode,
    setActiveCapabilityCode,
    registerToolContributions,
  }), [activeCapabilityCode, activeToolKey, registerToolContributions]);

  return (
    <WorkspaceGlobalToolRailContext.Provider value={contextValue}>
      <div
        className="relative flex h-full min-h-0 flex-1 overflow-hidden"
        data-testid="workspace-global-tool-shell"
      >
        <main className="flex h-full min-h-0 flex-1 overflow-hidden">
          {children}
        </main>
        {activeContribution?.renderPanel ? (
          <aside
            className={`flex h-full ${WORKSPACE_RIGHT_REGION_PANEL_WIDTH_CLASS} shrink-0 flex-col border-l border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950`}
            data-testid="workspace-global-tool-panel"
            data-active-tool-key={activeContribution.key}
          >
            <div className="flex h-10 shrink-0 items-center justify-between border-b border-gray-200 px-3 dark:border-gray-800">
              <div className="min-w-0 truncate text-xs font-semibold text-gray-700 dark:text-gray-200">
                {activeContribution.label}
              </div>
              <button
                type="button"
                aria-label={`Close ${activeContribution.label}`}
                className="inline-flex h-7 w-7 items-center justify-center rounded text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-100"
                onClick={() => setActiveToolKey(null)}
              >
                <X aria-hidden="true" className="h-4 w-4" />
              </button>
            </div>
            <div className={WORKSPACE_RIGHT_REGION_PANEL_BODY_CLASS}>
              <React.Suspense fallback={<WorkspaceToolPanelLoadingState label={activeContribution.label} />}>
                {activeContribution.renderPanel()}
              </React.Suspense>
            </div>
          </aside>
        ) : null}
        <WorkspaceToolRail
          ariaLabel="Workspace tools"
          testId="workspace-global-tool-rail"
          groups={groups}
        />
      </div>
    </WorkspaceGlobalToolRailContext.Provider>
  );
}
