'use client';

import React from 'react';
import { Activity, GitGraph, Package, PanelRight, Settings as SettingsIcon, Smartphone, X } from 'lucide-react';

import {
  WorkspaceToolRail,
  WorkspaceToolRailButton,
  type WorkspaceToolRailGroup,
} from '@/components/workspace/WorkspaceToolRail';
import { useCapabilityWorkbenchPlacement } from '@/components/capabilities/workbench/CapabilityWorkbenchResponsiveFrame';
import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { getApiBaseUrl } from '@/lib/api-url';
import { openAppRouteInNewWindow } from '@/lib/navigation/openAppRouteInNewWindow';
import {
  WORKSPACE_RIGHT_REGION_PANEL_BODY_CLASS,
  WORKSPACE_RIGHT_REGION_PANEL_WIDTH_CLASS,
  type WorkspaceRightRegionGroup,
} from '@/lib/workspace-right-region/workspace-right-region-contract';
import {
  WorkspaceGlobalToolRailContext,
  type WorkspaceGlobalToolContribution,
} from './useWorkspaceGlobalToolRail';
import {
  CapabilityWorkbenchMobileFloatingControlsContext,
  type CapabilityWorkbenchMobileFloatingControl,
  useCapabilityWorkbenchMobileFloatingControlsBridgePublisher,
} from '@/components/capabilities/workbench/useCapabilityWorkbenchMobileFloatingControls';

const WorkspaceRunsPanel = React.lazy(() => import('../capability-ui-hosts/WorkspaceRunsPanel'));
const WorkspaceSettingsToolPanel = React.lazy(() => import('../capability-ui-hosts/WorkspaceSettingsToolPanel'));
const WorkspacePackToolPanel = React.lazy(() => import('../capability-ui-hosts/WorkspacePackToolPanel'));
const MotionSourceRailPanel = React.lazy(() => import('@/components/workspace/device-binding/MotionSourceRailPanel'));

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

function resolveVisibleMobileFloatingControls(
  registeredControls: Record<string, CapabilityWorkbenchMobileFloatingControl[]>,
): CapabilityWorkbenchMobileFloatingControl[] {
  const controlMap = new Map<string, CapabilityWorkbenchMobileFloatingControl>();
  Object.values(registeredControls)
    .flat()
    .forEach((control) => {
      controlMap.set(control.key, control);
    });
  return [...controlMap.values()].sort((left, right) => (
    left.order - right.order || left.key.localeCompare(right.key)
  ));
}

interface WorkspaceGlobalToolRailProviderProps {
  workspaceId: string;
  children: React.ReactNode;
}

export default function WorkspaceGlobalToolRailProvider({
  workspaceId,
  children,
}: WorkspaceGlobalToolRailProviderProps) {
  const apiUrl = getApiBaseUrl();
  const workspaceData = useWorkspaceDataOptional();
  const placement = useCapabilityWorkbenchPlacement();
  const railPlacement = placement === 'mobile' ? 'tray' : 'side';
  const [activeToolKey, setActiveToolKey] = React.useState<string | null>(null);
  const [activeCapabilityCode, setActiveCapabilityCode] = React.useState<string | null>(null);
  const [mobileTrayOpen, setMobileTrayOpen] = React.useState(false);
  const [registeredScopeContributions, setRegisteredScopeContributions] = React.useState<Record<string, WorkspaceGlobalToolContribution[]>>({});
  const [registeredMobileFloatingControls, setRegisteredMobileFloatingControls] = React.useState<Record<string, CapabilityWorkbenchMobileFloatingControl[]>>({});
  const deepLinkedToolHrefRef = React.useRef<string | null>(null);
  const mobileTrayAnchorRef = React.useRef<HTMLDivElement | null>(null);
  const mobilePanelRef = React.useRef<HTMLElement | null>(null);
  const activeExecutionCount = (workspaceData?.executions || []).filter((execution) => (
    isActiveExecutionStatus(execution.status)
  )).length;
  const isMobilePlacement = placement === 'mobile';

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

  const registerMobileFloatingControls = React.useCallback((
    scopeId: string,
    controls: CapabilityWorkbenchMobileFloatingControl[],
  ) => {
    setRegisteredMobileFloatingControls((current) => ({
      ...current,
      [scopeId]: controls,
    }));
    return () => {
      setRegisteredMobileFloatingControls((current) => {
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
      key: 'core:motion_source',
      id: 'motion_source',
      label: 'Motion Source',
      icon: <Smartphone aria-hidden="true" className="h-4 w-4" />,
      group: 'runtime',
      order: 30,
      testId: 'workspace-motion-source-tool',
      renderPanel: () => (
        <MotionSourceRailPanel workspaceId={workspaceId} apiUrl={apiUrl} />
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
        openAppRouteInNewWindow(`/mindscape/canvas?workspaceId=${encodeURIComponent(workspaceId)}`);
      },
    },
  ], [activeCapabilityCode, activeExecutionCount, apiUrl, workspaceId]);

  const visibleContributions = React.useMemo(
    () => resolveVisibleContributions(coreContributions, registeredScopeContributions),
    [coreContributions, registeredScopeContributions],
  );
  const activeContribution = React.useMemo(
    () => visibleContributions.find((contribution) => contribution.key === activeToolKey) || null,
    [activeToolKey, visibleContributions],
  );
  const visibleMobileFloatingControls = React.useMemo(() => resolveVisibleMobileFloatingControls(registeredMobileFloatingControls), [registeredMobileFloatingControls]);

  React.useEffect(() => {
    if (activeToolKey && (!activeContribution || !activeContribution.renderPanel)) {
      setActiveToolKey(null);
    }
  }, [activeContribution, activeToolKey]);

  React.useEffect(() => {
    if (!isMobilePlacement) {
      setMobileTrayOpen(false);
      return;
    }
    if (activeContribution?.renderPanel) {
      setMobileTrayOpen(true);
    }
  }, [activeContribution, isMobilePlacement]);

  React.useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    if (deepLinkedToolHrefRef.current === window.location.href) {
      return;
    }
    const toolId = new URLSearchParams(window.location.search).get('tool');
    if (!toolId) {
      deepLinkedToolHrefRef.current = window.location.href;
      return;
    }
    const linkedContribution = visibleContributions.find((contribution) => (
      contribution.id === toolId || contribution.key === toolId
    ));
    if (!linkedContribution?.renderPanel) {
      return;
    }
    deepLinkedToolHrefRef.current = window.location.href;
    setActiveToolKey(linkedContribution.key);
  }, [visibleContributions]);

  React.useEffect(() => {
    if (!isMobilePlacement || !mobileTrayOpen || typeof document === 'undefined') {
      return undefined;
    }

    function dismissMobileTray(event?: Event) {
      const target = event?.target;
      if (target instanceof Node) {
        if (mobileTrayAnchorRef.current?.contains(target) || mobilePanelRef.current?.contains(target)) {
          return;
        }
      }

      document.removeEventListener('click', dismissMobileTray, true);
      document.removeEventListener('scroll', dismissMobileTray, true);
      window.removeEventListener('scroll', dismissMobileTray, true);
      setMobileTrayOpen(false);
      setActiveToolKey(null);
    }

    document.addEventListener('click', dismissMobileTray, true);
    document.addEventListener('scroll', dismissMobileTray, { capture: true, passive: true });
    window.addEventListener('scroll', dismissMobileTray, { capture: true, passive: true });

    return () => {
      document.removeEventListener('click', dismissMobileTray, true);
      document.removeEventListener('scroll', dismissMobileTray, true);
      window.removeEventListener('scroll', dismissMobileTray, true);
    };
  }, [isMobilePlacement, mobileTrayOpen]);

  const handleContributionClick = React.useCallback((contribution: WorkspaceGlobalToolContribution) => {
    if (contribution.disabled) {
      return;
    }
    if (contribution.onSelect) {
      setActiveToolKey(null);
      setMobileTrayOpen(false);
      contribution.onSelect();
      return;
    }
    if (contribution.renderPanel) {
      setMobileTrayOpen(true);
      setActiveToolKey((current) => (current === contribution.key ? null : contribution.key));
    }
  }, []);

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
                    onClick={() => handleContributionClick(contribution)}
                  />
                )}
              </React.Fragment>
            ))}
          </>
        ),
      }));
  }, [activeToolKey, handleContributionClick, visibleContributions]);

  const contextValue = React.useMemo(() => ({
    activeToolKey,
    setActiveToolKey,
    activeCapabilityCode,
    setActiveCapabilityCode,
    registerToolContributions,
  }), [activeCapabilityCode, activeToolKey, registerToolContributions]);
  const mobileFloatingControlsContextValue = React.useMemo(() => ({ registerControls: registerMobileFloatingControls }), [registerMobileFloatingControls]);
  useCapabilityWorkbenchMobileFloatingControlsBridgePublisher(mobileFloatingControlsContextValue);

  const workspaceToolRail = (
    <WorkspaceToolRail
      ariaLabel="Workspace tools"
      testId="workspace-global-tool-rail"
      placement={railPlacement}
      groups={groups}
    />
  );
  const workspaceToolFloatingControl = React.useMemo<CapabilityWorkbenchMobileFloatingControl>(() => ({
    key: 'workspace-global-tools',
    order: 20,
    render: () => (
      <div
        ref={mobileTrayAnchorRef}
        className="flex flex-col items-start gap-2"
        data-testid="workspace-global-tool-tray-anchor"
      >
        <button
          type="button"
          className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-gray-200 bg-white/95 text-gray-700 shadow-lg backdrop-blur transition hover:bg-white dark:border-gray-800 dark:bg-gray-950/95 dark:text-gray-200"
          aria-label={mobileTrayOpen ? 'Close workspace tools' : 'Open workspace tools'}
          aria-pressed={mobileTrayOpen}
          data-testid="workspace-global-tool-tray-toggle"
          onClick={() => {
            if (mobileTrayOpen) {
              setMobileTrayOpen(false);
              setActiveToolKey(null);
              return;
            }
            setMobileTrayOpen(true);
          }}
        >
          {mobileTrayOpen ? (
            <X aria-hidden="true" className="h-4 w-4" />
          ) : (
            <PanelRight aria-hidden="true" className="h-4 w-4" />
          )}
        </button>
        {mobileTrayOpen ? workspaceToolRail : null}
      </div>
    ),
  }), [mobileTrayOpen, workspaceToolRail]);
  const mobileFloatingControls = React.useMemo(() => (
    isMobilePlacement
      ? [workspaceToolFloatingControl, ...visibleMobileFloatingControls].sort((left, right) => (
        left.order - right.order || left.key.localeCompare(right.key)
      ))
      : []
  ), [isMobilePlacement, visibleMobileFloatingControls, workspaceToolFloatingControl]);

  const workspaceToolPanel = activeContribution?.renderPanel ? (
    <aside
      ref={mobilePanelRef}
      className={isMobilePlacement
        ? 'absolute left-14 top-[calc(0.5rem+env(safe-area-inset-top,0px))] z-40 flex max-h-[min(78dvh,36rem)] w-[min(20rem,calc(100vw-4.75rem))] max-w-[calc(100vw-4.75rem)] flex-col overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xl dark:border-gray-800 dark:bg-gray-950'
        : `flex h-full ${WORKSPACE_RIGHT_REGION_PANEL_WIDTH_CLASS} shrink-0 flex-col border-l border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950`}
      data-testid="workspace-global-tool-panel"
      data-active-tool-key={activeContribution.key}
      data-workbench-placement={placement}
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
  ) : null;

  return (
    <WorkspaceGlobalToolRailContext.Provider value={contextValue}>
      <CapabilityWorkbenchMobileFloatingControlsContext.Provider value={mobileFloatingControlsContextValue}>
        <div
          className="relative flex h-full min-h-0 flex-1 flex-col overflow-hidden md:flex-row"
          data-testid="workspace-global-tool-shell"
          data-workbench-placement={placement}
        >
          <main className="order-1 flex h-full min-h-0 flex-1 overflow-hidden md:order-none">
            {children}
          </main>
          {isMobilePlacement ? (
            <>
              {workspaceToolPanel}
              {mobileFloatingControls.length > 0 ? (
                <div
                  className="absolute left-2 top-[calc(0.5rem+env(safe-area-inset-top,0px))] z-50 flex flex-col items-start gap-2"
                  data-testid="workspace-mobile-floating-controls"
                >
                  {mobileFloatingControls.map((control) => (
                    <div key={control.key} className="shrink-0">
                      {control.render()}
                    </div>
                  ))}
                </div>
              ) : null}
            </>
          ) : (
            <>
              {workspaceToolPanel}
              {workspaceToolRail}
            </>
          )}
        </div>
      </CapabilityWorkbenchMobileFloatingControlsContext.Provider>
    </WorkspaceGlobalToolRailContext.Provider>
  );
}
