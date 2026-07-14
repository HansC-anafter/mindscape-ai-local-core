'use client';

import React from 'react';
import { X } from 'lucide-react';

import {
  WorkspaceToolRail,
  WorkspaceToolRailButton,
  type WorkspaceToolRailGroup,
} from '@/components/workspace/WorkspaceToolRail';
import { useCapabilityWorkbenchPlacement } from '@/components/capabilities/workbench/CapabilityWorkbenchResponsiveFrame';
import { useToolRailPanelToggleShortcut } from '@/components/capabilities/workbench/useToolRailPanelToggleShortcut';
import { ExecutionContextProvider } from '@/contexts/ExecutionContextContext';
import {
  WorkspaceDataProvider,
  useWorkspaceDataOptional,
  type WorkspaceDataInitialLoadProfile,
} from '@/contexts/WorkspaceDataContext';
import { getApiBaseUrl } from '@/lib/api-url';
import {
  WORKSPACE_RIGHT_REGION_PANEL_BODY_CLASS,
  WORKSPACE_RIGHT_REGION_PANEL_WIDTH_CLASS,
  type WorkspaceRightRegionGroup,
} from '@/lib/workspace-right-region/workspace-right-region-contract';
import { useKeyboardShortcuts } from '@/lib/keyboard-shortcuts';
import {
  WorkspaceGlobalToolRailContext,
  type WorkspaceGlobalToolContribution,
} from '../components/useWorkspaceGlobalToolRail';
import {
  WorkspaceMobileHostToolTray,
  useWorkspaceMobileHostToolTray,
} from '../components/WorkspaceMobileHostToolTray';
import {
  GROUP_LABELS,
  WORKSPACE_ACTIVE_PANEL_TOGGLE_BINDING_ID,
  WORKSPACE_TOOL_RAIL_COMMAND_ID,
  bindingIdForContribution,
  buildCoreWorkspaceToolContributions,
  groupOrder,
  isActiveExecutionStatus,
  resolveVisibleContributions,
  shortcutOwnerForContribution,
  sortContributions,
} from './capabilityHostRuntimeFrame/workspaceToolContributions';

interface CapabilityHostRuntimeFrameProps {
  workspaceId: string;
  initialLoadProfile?: WorkspaceDataInitialLoadProfile;
  remoteSurfaceMode?: boolean;
  children: React.ReactNode;
}

function WorkspaceToolPanelLoadingState({ label }: { label: string }) {
  return (
    <div className="flex h-full items-center justify-center p-3 text-xs text-gray-500 dark:text-gray-400">
      Loading {label}...
    </div>
  );
}

function CapabilityHostToolRailProvider({
  workspaceId,
  remoteSurfaceMode,
  children,
}: {
  workspaceId: string;
  remoteSurfaceMode: boolean;
  children: React.ReactNode;
}) {
  const apiUrl = getApiBaseUrl();
  const workspaceData = useWorkspaceDataOptional();
  const {
    activateScope,
    getCommandAriaShortcut,
    getCommandShortcut,
    registerCommand,
  } = useKeyboardShortcuts();
  const placement = useCapabilityWorkbenchPlacement();
  const shortcutScope = `workspace:${workspaceId}`;
  const isMobilePlacement = placement === 'mobile';
  const [activeToolKey, setActiveToolKey] = React.useState<string | null>(null);
  const [activeCapabilityCode, setActiveCapabilityCode] = React.useState<string | null>(null);
  const [lastPanelToolKey, setLastPanelToolKey] = React.useState<string | null>(null);
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

  const coreContributions = React.useMemo<WorkspaceGlobalToolContribution[]>(() => (
    buildCoreWorkspaceToolContributions({
      workspaceId,
      apiUrl,
      activeCapabilityCode,
      activeExecutionCount,
      remoteSurfaceMode,
    })
  ), [activeCapabilityCode, activeExecutionCount, apiUrl, remoteSurfaceMode, workspaceId]);

  const visibleContributions = React.useMemo(
    () => resolveVisibleContributions(coreContributions, registeredScopeContributions),
    [coreContributions, registeredScopeContributions],
  );
  const activeContribution = React.useMemo(
    () => visibleContributions.find((contribution) => contribution.key === activeToolKey) || null,
    [activeToolKey, visibleContributions],
  );
  const dismissMobileTray = React.useCallback(() => {
    setActiveToolKey(null);
  }, []);
  const {
    anchorRef: mobileTrayAnchorRef,
    panelRef: mobilePanelRef,
    open: mobileTrayOpen,
    close: closeMobileTray,
    show: showMobileTray,
    toggle: toggleMobileTray,
  } = useWorkspaceMobileHostToolTray({
    enabled: isMobilePlacement,
    activePanelOpen: Boolean(activeContribution?.renderPanel),
    onDismiss: dismissMobileTray,
  });

  React.useEffect(() => {
    if (activeToolKey && (!activeContribution || !activeContribution.renderPanel)) {
      setActiveToolKey(null);
    }
  }, [activeContribution, activeToolKey]);

  React.useEffect(() => {
    return activateScope(shortcutScope);
  }, [activateScope, shortcutScope]);

  React.useEffect(() => {
    if (activeContribution?.renderPanel) {
      setLastPanelToolKey(activeContribution.key);
    }
  }, [activeContribution]);

  const activateContribution = React.useCallback((contribution: WorkspaceGlobalToolContribution) => {
    if (contribution.disabled) {
      return;
    }
    if (contribution.onSelect) {
      setActiveToolKey(null);
      if (isMobilePlacement) {
        closeMobileTray();
      }
      contribution.onSelect();
      return;
    }
    if (contribution.renderPanel) {
      if (isMobilePlacement) {
        showMobileTray();
      }
      setActiveToolKey((current) => (current === contribution.key ? null : contribution.key));
    }
  }, [closeMobileTray, isMobilePlacement, showMobileTray]);

  React.useEffect(() => {
    const disposers = visibleContributions
      .filter((contribution) => Boolean(contribution.defaultShortcut))
      .map((contribution) => {
        const owner = shortcutOwnerForContribution(contribution);
        return registerCommand({
          bindingId: bindingIdForContribution(contribution),
          commandId: WORKSPACE_TOOL_RAIL_COMMAND_ID,
          label: contribution.label,
          ownerType: owner.ownerType,
          ownerId: owner.ownerId,
          ownerLabel: owner.ownerLabel,
          defaultShortcut: contribution.defaultShortcut,
          scope: shortcutScope,
          preventDefault: true,
          enabled: contribution.disabled !== true,
          action: () => activateContribution(contribution),
        });
      });
    return () => disposers.forEach((dispose) => dispose());
  }, [activateContribution, registerCommand, shortcutScope, visibleContributions]);

  const toggleActiveWorkspacePanel = React.useCallback(() => {
    if (activeContribution?.renderPanel) {
      setActiveToolKey(null);
      return;
    }
    const lastContribution = visibleContributions.find((contribution) => (
      contribution.key === lastPanelToolKey
      && contribution.disabled !== true
      && Boolean(contribution.renderPanel)
    ));
    if (lastContribution) {
      if (isMobilePlacement) {
        showMobileTray();
      }
      setActiveToolKey(lastContribution.key);
    }
  }, [activeContribution, isMobilePlacement, lastPanelToolKey, showMobileTray, visibleContributions]);

  useToolRailPanelToggleShortcut({
    bindingId: WORKSPACE_ACTIVE_PANEL_TOGGLE_BINDING_ID,
    scope: shortcutScope,
    label: 'Toggle active workspace tool panel',
    ownerType: 'core',
    ownerId: 'workspace',
    ownerLabel: 'Workspace',
    enabled: Boolean(activeContribution?.renderPanel || lastPanelToolKey),
    shortcutPriority: activeContribution?.renderPanel ? 350 : undefined,
    onToggle: toggleActiveWorkspacePanel,
  });

  const groups = React.useMemo<WorkspaceToolRailGroup[]>(() => {
    const grouped = new Map<WorkspaceRightRegionGroup, WorkspaceGlobalToolContribution[]>();
    visibleContributions.forEach((contribution) => {
      const items = grouped.get(contribution.group) || [];
      items.push(contribution);
      grouped.set(contribution.group, items);
    });

    return [...grouped.entries()]
      .sort(([leftGroup], [rightGroup]) => groupOrder(leftGroup) - groupOrder(rightGroup))
      .map(([group, contributions]) => ({
        id: `workspace-global-${group}`,
        label: GROUP_LABELS[group],
        testId: `workspace-global-tool-group-${group}`,
        children: (
          <>
            {contributions.sort(sortContributions).map((contribution) => {
              const bindingId = bindingIdForContribution(contribution);
              const currentShortcut = getCommandShortcut(bindingId, contribution.defaultShortcut);
              const ariaShortcut = getCommandAriaShortcut(bindingId, contribution.defaultShortcut);
              return (
                <React.Fragment key={contribution.key}>
                  {contribution.renderRailButton ? contribution.renderRailButton() : (
                    <WorkspaceToolRailButton
                      label={contribution.label}
                      icon={contribution.icon}
                      shortcut={currentShortcut}
                      ariaKeyShortcuts={ariaShortcut}
                      active={activeToolKey === contribution.key}
                      disabled={contribution.disabled}
                      badge={contribution.badge}
                      testId={contribution.testId}
                      onClick={() => activateContribution(contribution)}
                    />
                  )}
                </React.Fragment>
              );
            })}
          </>
        ),
      }));
  }, [activeToolKey, activateContribution, getCommandAriaShortcut, getCommandShortcut, visibleContributions]);

  const contextValue = React.useMemo(() => ({
    activeToolKey,
    setActiveToolKey,
    activeCapabilityCode,
    setActiveCapabilityCode,
    registerToolContributions,
  }), [activeCapabilityCode, activeToolKey, registerToolContributions]);

  const workspaceToolRail = (
    <WorkspaceToolRail
      ariaLabel="Capability host tools"
      testId="workspace-global-tool-rail"
      placement={isMobilePlacement ? 'tray' : 'side'}
      groups={groups}
    />
  );

  const workspaceToolPanel = activeContribution?.renderPanel ? (
    <aside
      ref={mobilePanelRef}
      className={isMobilePlacement
        ? 'absolute right-14 top-[calc(0.5rem+env(safe-area-inset-top,0px))] bottom-[calc(4.75rem+env(safe-area-inset-bottom,0px))] z-40 flex max-h-none w-[min(20rem,calc(100vw-4.75rem))] max-w-[calc(100vw-4.75rem)] flex-col overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xl dark:border-gray-800 dark:bg-gray-950'
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
          onClick={() => {
            setActiveToolKey(null);
          }}
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
      <div
        className="relative flex h-full min-h-0 w-full min-w-0 flex-1 overflow-hidden"
        data-testid="capability-host-tool-shell"
        data-workbench-placement={placement}
      >
        <main className="flex h-full min-h-0 min-w-0 flex-1 overflow-hidden">
          {children}
        </main>
        {isMobilePlacement ? (
          <WorkspaceMobileHostToolTray
            anchorRef={mobileTrayAnchorRef}
            open={mobileTrayOpen}
            onToggle={toggleMobileTray}
            rail={workspaceToolRail}
            panel={workspaceToolPanel}
          />
        ) : (
          <>
            {workspaceToolPanel}
            <div
              className="flex shrink-0"
              data-testid="capability-host-rail-slot"
            >
              {workspaceToolRail}
            </div>
          </>
        )}
      </div>
    </WorkspaceGlobalToolRailContext.Provider>
  );
}

export default function CapabilityHostRuntimeFrame({
  workspaceId,
  initialLoadProfile,
  remoteSurfaceMode = false,
  children,
}: CapabilityHostRuntimeFrameProps) {
  return (
    <WorkspaceDataProvider workspaceId={workspaceId} initialLoadProfile={initialLoadProfile}>
      <ExecutionContextProvider workspaceId={workspaceId}>
        <CapabilityHostToolRailProvider
          workspaceId={workspaceId}
          remoteSurfaceMode={remoteSurfaceMode}
        >
          {children}
        </CapabilityHostToolRailProvider>
      </ExecutionContextProvider>
    </WorkspaceDataProvider>
  );
}
