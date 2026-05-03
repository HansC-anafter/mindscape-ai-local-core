'use client';

import type { Ref } from 'react';

import { AOLRuntimeShellContext, type AOLRuntimeShellProviderProps } from './AOLRuntimeShellContext';
import { RuntimeObjectPanel } from './RuntimeObjectPanel';
import { RuntimeShellPanel } from './RuntimeShellPanel';
import { RuntimeShellToolRail } from './RuntimeShellToolRail';
import { useAOLRuntimeShellHostController } from './useAOLRuntimeShellHostController';

function AOLRuntimeShellProviderInner({
  children,
}: AOLRuntimeShellProviderProps) {
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

  return (
    <AOLRuntimeShellContext.Provider value={controller}>
      <div ref={shellRootRef as Ref<HTMLDivElement>} className="relative flex min-h-0 min-w-0 flex-1 flex-col">
        <div
          className="relative flex min-h-0 min-w-0 flex-1 overflow-hidden"
          data-testid="aol-workspace-region"
        >
          {children}
          <div
            className="pointer-events-none absolute inset-y-0 right-0 z-40 flex h-full items-stretch"
            data-testid="aol-shell-region"
          >
            {panelState.mode === 'idle' || panelState.mode === 'meeting_opened' ? null : (
              <div className="pointer-events-auto flex h-full items-start px-3 pb-4 pt-16">
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
            )}
            <RuntimeShellToolRail
              state={panelState}
              canOpenFlow={canOpenFlow}
              onRequestObjectTargeting={requestObjectTargeting}
              onCancelObjectTargeting={cancelObjectTargeting}
              onOpenFlow={openRuntimeFlowFromRail}
            />
          </div>
        </div>
        <RuntimeShellPanel
          state={panelState}
          paneHeight={meetingPaneHeight}
          onClose={closeCurrentMeeting}
          onResizeStart={beginMeetingPaneResize}
          onSizePreset={setMeetingPaneSizePreset}
          onSwitchObject={requestObjectTargeting}
        />
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
