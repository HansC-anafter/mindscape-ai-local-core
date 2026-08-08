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
import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { getApiBaseUrl } from '@/lib/api-url';
import { useT } from '@/lib/i18n';
import { useKeyboardShortcuts } from '@/lib/keyboard-shortcuts';
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
  useWorkspaceCoreToolContributions,
  WorkspaceToolPanelLoadingState,
} from './workspaceGlobalToolRailCoreContributions';
import {
  bindingIdForContribution,
  GROUP_LABELS,
  GROUP_ORDER,
  isActiveExecutionStatus,
  resolveVisibleContributions,
  shortcutOwnerForContribution,
  sortContributions,
  WORKSPACE_ACTIVE_PANEL_TOGGLE_BINDING_ID,
  WORKSPACE_TOOL_RAIL_COMMAND_ID,
} from './workspaceGlobalToolRailModel';
import {
  WorkspaceMobileHostToolTray,
  useWorkspaceMobileHostToolTray,
} from './WorkspaceMobileHostToolTray';
import { WorkspaceInteractionIngressHost } from '@/components/workspace/interaction/WorkspaceInteractionIngressHost';

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
  const t = useT();
  const {
    activateScope,
    getCommandAriaShortcut,
    getCommandShortcut,
    registerCommand,
  } = useKeyboardShortcuts();
  const placement = useCapabilityWorkbenchPlacement();
  const shortcutScope = `workspace:${workspaceId}`;
  const railPlacement = placement === 'mobile' ? 'tray' : 'side';
  const [activeToolKey, setActiveToolKey] = React.useState<string | null>(null);
  const [activeCapabilityCode, setActiveCapabilityCode] = React.useState<string | null>(null);
  const [lastPanelToolKey, setLastPanelToolKey] = React.useState<string | null>(null);
  const [registeredScopeContributions, setRegisteredScopeContributions] = React.useState<Record<string, WorkspaceGlobalToolContribution[]>>({});
  const deepLinkedToolHrefRef = React.useRef<string | null>(null);
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

  const coreContributions = useWorkspaceCoreToolContributions({
    activeCapabilityCode,
    activeExecutionCount,
    apiUrl,
    workspaceId,
  });

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
  const handleContributionClick = activateContribution;

  React.useEffect(() => {
    const disposers = visibleContributions
      .filter((contribution) => Boolean(contribution.defaultShortcut))
      .map((contribution) => {
        const owner = shortcutOwnerForContribution(contribution);
        const ownerLabel = owner.ownerLabel.startsWith('workspaceToolOwner')
          ? t(owner.ownerLabel)
          : owner.ownerLabel;
        return registerCommand({
          bindingId: bindingIdForContribution(contribution),
          commandId: WORKSPACE_TOOL_RAIL_COMMAND_ID,
          label: contribution.label,
          ownerType: owner.ownerType,
          ownerId: owner.ownerId,
          ownerLabel,
          defaultShortcut: contribution.defaultShortcut,
          scope: shortcutScope,
          preventDefault: true,
          enabled: contribution.disabled !== true,
          action: () => activateContribution(contribution),
        });
      });
    return () => disposers.forEach((dispose) => dispose());
  }, [activateContribution, registerCommand, shortcutScope, t, visibleContributions]);

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
    if (!lastContribution) {
      return;
    }
    if (isMobilePlacement) {
      showMobileTray();
    }
    setActiveToolKey(lastContribution.key);
  }, [activeContribution, isMobilePlacement, lastPanelToolKey, showMobileTray, visibleContributions]);

  useToolRailPanelToggleShortcut({
    bindingId: WORKSPACE_ACTIVE_PANEL_TOGGLE_BINDING_ID,
    scope: shortcutScope,
    label: t('workspaceToolPanelToggleActive'),
    ownerType: 'core',
    ownerId: 'workspace',
    ownerLabel: t('workspaceToolOwnerWorkspace'),
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
      .sort(([leftGroup], [rightGroup]) => GROUP_ORDER[leftGroup] - GROUP_ORDER[rightGroup])
      .map(([group, contributions]) => ({
        id: `workspace-global-${group}`,
        label: t(GROUP_LABELS[group]),
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
                      onClick={() => handleContributionClick(contribution)}
                    />
                  )}
                </React.Fragment>
              );
            })}
          </>
        ),
      }));
  }, [activeToolKey, getCommandAriaShortcut, getCommandShortcut, t, handleContributionClick, visibleContributions]);

  const contextValue = React.useMemo(() => ({
    activeToolKey,
    setActiveToolKey,
    activeCapabilityCode,
    setActiveCapabilityCode,
    registerToolContributions,
  }), [activeCapabilityCode, activeToolKey, registerToolContributions]);
  const workspaceToolRail = (
    <WorkspaceToolRail
      ariaLabel={t('workspaceToolRailAriaWorkspace')}
      testId="workspace-global-tool-rail"
      placement={railPlacement}
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
          aria-label={t('workspaceToolPanelClose', { label: activeContribution.label })}
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
      <WorkspaceInteractionIngressHost workspaceId={workspaceId}>
        <div
          className="relative flex h-full min-h-0 flex-1 flex-col overflow-hidden md:flex-row"
          data-testid="workspace-global-tool-shell"
          data-workbench-placement={placement}
        >
          <main className="order-1 flex h-full min-h-0 flex-1 overflow-hidden md:order-none">
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
              {workspaceToolRail}
            </>
          )}
        </div>
      </WorkspaceInteractionIngressHost>
    </WorkspaceGlobalToolRailContext.Provider>
  );
}
