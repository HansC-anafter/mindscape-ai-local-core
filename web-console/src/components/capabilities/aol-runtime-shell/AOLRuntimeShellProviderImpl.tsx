'use client';

import React, { Suspense, lazy, useEffect, useMemo, useState, type ComponentType, type Ref } from 'react';

import { useT } from '@/lib/i18n';
import {
  useWorkspaceGlobalToolContributions,
  type WorkspaceGlobalToolContribution,
} from '@/app/workspaces/[workspaceId]/components/useWorkspaceGlobalToolRail';
import { AOLRuntimeShellContext, type AOLRuntimeShellProviderProps } from './AOLRuntimeShellContext';
import { RuntimeShellPanelFallback } from './RuntimeShellPanelFallback';
import type { RuntimeShellPanelProps } from './RuntimeShellPanel';
import { RuntimeObjectPanel } from './RuntimeObjectPanel';
import { RuntimeObjectSelectionAnchor } from './RuntimeObjectSelectionAnchor';
import { RuntimeFlowAnchor } from './RuntimeFlowAnchor';
import { useAOLRuntimeShellHostController } from './useAOLRuntimeShellHostController';

type RuntimeShellPanelModule = { default: ComponentType<RuntimeShellPanelProps> };
type RuntimeShellPanelImport = {
  RuntimeShellPanel: ComponentType<RuntimeShellPanelProps>;
  preloadRuntimeShellPanelBody: () => Promise<unknown>;
};

let runtimeShellPanelPromise: Promise<RuntimeShellPanelModule> | null = null;
let runtimeShellPanelResolved = false;

function loadRuntimeShellPanelModule(): Promise<RuntimeShellPanelModule> {
  runtimeShellPanelPromise ??= import('./RuntimeShellPanel').then(async (module: RuntimeShellPanelImport) => {
    await module.preloadRuntimeShellPanelBody();
    return {
      default: module.RuntimeShellPanel,
    };
  }).then((module) => {
    runtimeShellPanelResolved = true;
    return module;
  });
  return runtimeShellPanelPromise;
}

const RuntimeShellPanelLazy = lazy(loadRuntimeShellPanelModule);

function AOLRuntimeShellProviderInner({
  children,
}: AOLRuntimeShellProviderProps) {
  const t = useT();
  const [runtimeShellPanelLoadState, setRuntimeShellPanelLoadState] = useState(
    runtimeShellPanelResolved ? 'loaded' : 'idle',
  );
  const {
    shellRootRef,
    panelState,
    meetingPaneHeight,
    canOpenFlow,
    controller,
    requestObjectTargeting,
    cancelObjectTargeting,
    clearCurrentObject,
    attachCurrentObject,
    openCurrentMeeting,
    closeCurrentMeeting,
    changeContextRole,
    selectCandidateObject,
    beginMeetingPaneResize,
    setMeetingPaneSizePreset,
    openRuntimeFlowFromRail,
  } = useAOLRuntimeShellHostController();
  const shouldRenderMeetingPane = panelState.mode === 'meeting_opened' && Boolean(panelState.activeSurface);
  const objectLabel = panelState.mode === 'selecting'
    ? t('aolRuntimeShellCancelObjectSelection')
    : t('aolRuntimeShellSelectObject');
  const objectHelper = panelState.mode === 'meeting_opened'
    ? t('aolRuntimeShellSelectAnotherObject')
    : objectLabel;
  const flowLabel = panelState.mode === 'meeting_opened'
    ? t('aolRuntimeShellFlowOpen')
    : canOpenFlow
      ? t('aolRuntimeShellOpenFlow')
      : t('aolRuntimeShellFlowUnavailable');
  const aolToolContributions = useMemo<WorkspaceGlobalToolContribution[]>(() => [{
    key: 'aol:object',
    id: 'object',
    label: objectLabel,
    group: 'runtime',
    order: 10,
    testId: 'aol-object-tool',
    renderRailButton: () => (
      <RuntimeObjectSelectionAnchor
        state={panelState}
        onRequestObjectTargeting={requestObjectTargeting}
        onCancelObjectTargeting={cancelObjectTargeting}
        label={objectLabel}
        helper={objectHelper}
        tone="light"
      />
    ),
  }, {
    key: 'aol:flow',
    id: 'flow',
    label: flowLabel,
    group: 'runtime',
    order: 20,
    testId: 'aol-runtime-flow-tool',
    renderRailButton: () => (
      <RuntimeFlowAnchor
        state={panelState}
        canOpenFlow={canOpenFlow}
        label={flowLabel}
        onOpenFlow={openRuntimeFlowFromRail}
        tone="light"
      />
    ),
  }], [
    canOpenFlow,
    cancelObjectTargeting,
    flowLabel,
    objectHelper,
    objectLabel,
    openRuntimeFlowFromRail,
    panelState,
    requestObjectTargeting,
  ]);

  useWorkspaceGlobalToolContributions('aol-runtime-shell', aolToolContributions);

  useEffect(() => {
    if (!shouldRenderMeetingPane) {
      setRuntimeShellPanelLoadState(runtimeShellPanelResolved ? 'loaded' : 'idle');
      return;
    }

    let cancelled = false;
    setRuntimeShellPanelLoadState(runtimeShellPanelResolved ? 'loaded' : 'preloading');

    void loadRuntimeShellPanelModule()
      .then(() => {
        if (!cancelled) {
          setRuntimeShellPanelLoadState('loaded');
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setRuntimeShellPanelLoadState('failed');
        }
        console.error('[AOLRuntimeShellProvider] Failed to preload runtime shell panel:', error);
      });
    return () => {
      cancelled = true;
    };
  }, [shouldRenderMeetingPane]);

  return (
    <AOLRuntimeShellContext.Provider value={controller}>
      <div ref={shellRootRef as Ref<HTMLDivElement>} className="relative flex h-full min-h-0 min-w-0 flex-1 flex-col">
        <div
          className="relative flex min-h-0 min-w-0 flex-1 overflow-hidden"
          data-testid="aol-workspace-region"
          data-aol-mode={panelState.mode}
          data-aol-active-surface={panelState.activeSurface?.surfaceId || ''}
          data-aol-panel-loaded={runtimeShellPanelLoadState}
        >
          <div
            className="relative min-h-0 min-w-0 flex-1 overflow-hidden"
            data-testid="aol-shell-content-region"
          >
            {children}
            {panelState.mode === 'idle' || panelState.mode === 'meeting_opened' ? null : (
              <div
                className="pointer-events-none absolute inset-y-0 right-0 z-40 flex h-full items-start px-3 pb-4 pt-16"
                data-testid="aol-shell-object-panel-region"
              >
                <div className="pointer-events-auto">
                  <RuntimeObjectPanel
                    state={panelState}
                    onRequestObjectTargeting={requestObjectTargeting}
                    onCancelObjectTargeting={cancelObjectTargeting}
                    onClearCurrentObject={clearCurrentObject}
                    onAttachCurrentObject={attachCurrentObject}
                    onOpenCurrentMeeting={openCurrentMeeting}
                    onRoleChange={changeContextRole}
                    onSelectCandidate={selectCandidateObject}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
        {shouldRenderMeetingPane ? (
          <Suspense
            fallback={
              <RuntimeShellPanelFallback
                state={panelState}
                paneHeight={meetingPaneHeight}
                onClose={closeCurrentMeeting}
                onResizeStart={beginMeetingPaneResize}
                onSizePreset={setMeetingPaneSizePreset}
              />
            }
          >
            <RuntimeShellPanelLazy
              state={panelState}
              paneHeight={meetingPaneHeight}
              onClose={closeCurrentMeeting}
              onResizeStart={beginMeetingPaneResize}
              onSizePreset={setMeetingPaneSizePreset}
              onSwitchObject={requestObjectTargeting}
            />
          </Suspense>
        ) : null}
      </div>
    </AOLRuntimeShellContext.Provider>
  );
}

export function AOLRuntimeShellProviderImpl({
  workspaceId,
  children,
}: AOLRuntimeShellProviderProps) {
  return (
    <AOLRuntimeShellProviderInner workspaceId={workspaceId}>
      {children}
    </AOLRuntimeShellProviderInner>
  );
}

export const AddressableObjectHostProvider = AOLRuntimeShellProviderImpl;
