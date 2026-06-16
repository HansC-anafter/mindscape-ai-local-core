import React, { type ReactNode } from 'react';

import type {
  AddressableObjectSummary,
  AddressableSelectionTarget,
  ObjectMeetingAttachResponse,
} from '@/lib/addressable-object-layer';
import { MeetingConsoleDrawer } from './PropertiesInspector';
import { MeetingWorkbenchInspectorDock, type MeetingWorkbenchInspectorDockProps } from './MeetingWorkbenchInspectorDock';
import { MeetingWorkbenchSecondaryDrawer } from './MeetingWorkbenchSecondaryDrawer';
import { MeetingObjectContextPanel, MeetingSessionsPopover } from './MeetingContextPanels';
import { ObjectOutlinerPanel } from './ObjectOutlinerPanel';
import type { MeetingMissingContext } from './meetingWorkbenchStatus';
import type { MeetingWorkbenchSecondarySurface } from './meetingWorkbenchPanelLayoutState';
import type {
  GraphViewMode,
  MeetingInfoPanel,
  MeetingNode,
  MeetingSessionSummary,
  MeetingTranslate,
} from './meetingWorkbenchTypes';

type InspectorDockProps = Omit<MeetingWorkbenchInspectorDockProps, 'presentation' | 'railPlacement'>;

export interface MeetingWorkbenchSecondarySurfaceSlots {
  floatingPanel: ReactNode;
  compactSecondaryDrawer: ReactNode;
}

export function createMeetingWorkbenchSecondarySurfaceSlots({
  compactViewport,
  activeInfoPanel,
  activeSecondarySurface,
  graphViewMode,
  nodes,
  summary,
  selection,
  attachResponse,
  activeMeetingId,
  surfaceRoute,
  onSwitchObject,
  sessions,
  sessionsLoading,
  sessionsError,
  creatingSession,
  createSessionError,
  selectedNodeId,
  activeMissingContext,
  selectedNode,
  isConsoleOpen,
  onCreateSession,
  onRetrySessions,
  onSelectSession,
  onCloseInfoPanel,
  onCloseSecondary,
  onSelectNodeFromDrawer,
  onSelectMissingContextFromDrawer,
  inspectorDockProps,
  t,
}: {
  compactViewport: boolean;
  activeInfoPanel: MeetingInfoPanel | null;
  activeSecondarySurface: MeetingWorkbenchSecondarySurface | null;
  graphViewMode: GraphViewMode;
  nodes: MeetingNode[];
  summary: AddressableObjectSummary | null;
  selection: AddressableSelectionTarget | null;
  attachResponse: ObjectMeetingAttachResponse | null;
  activeMeetingId: string;
  surfaceRoute: string;
  onSwitchObject: () => void;
  sessions: MeetingSessionSummary[];
  sessionsLoading: boolean;
  sessionsError: string | null;
  creatingSession: boolean;
  createSessionError: string | null;
  selectedNodeId: string;
  activeMissingContext: MeetingMissingContext | null;
  selectedNode: MeetingNode | null;
  isConsoleOpen: boolean;
  onCreateSession: () => void | Promise<void>;
  onRetrySessions: () => void;
  onSelectSession: (session: MeetingSessionSummary) => void;
  onCloseInfoPanel: () => void;
  onCloseSecondary: () => void;
  onSelectNodeFromDrawer: (nodeId: string) => void;
  onSelectMissingContextFromDrawer: (context: MeetingMissingContext) => void;
  inspectorDockProps: InspectorDockProps;
  t: MeetingTranslate;
}): MeetingWorkbenchSecondarySurfaceSlots {
  const floatingPanel = !compactViewport ? (
    <>
      {activeInfoPanel === 'object' ? (
        <div className="pointer-events-none absolute left-3 top-3 z-30 h-[calc(100%-1.5rem)] w-[min(340px,calc(100%-1.5rem))]">
          <MeetingObjectContextPanel
            summary={summary}
            selection={selection}
            attachResponse={attachResponse}
            meetingId={activeMeetingId}
            surfaceRoute={surfaceRoute}
            onSwitchObject={onSwitchObject}
            onClose={onCloseInfoPanel}
          />
        </div>
      ) : null}
      {activeInfoPanel === 'sessions' ? (
        <div className="pointer-events-none absolute left-3 right-3 top-3 z-30 md:right-16">
          <MeetingSessionsPopover
            sessions={sessions}
            activeMeetingId={activeMeetingId}
            loading={sessionsLoading}
            error={sessionsError}
            creating={creatingSession}
            createError={createSessionError}
            onCreateSession={onCreateSession}
            onRetry={onRetrySessions}
            onSelectSession={onSelectSession}
            onClose={onCloseInfoPanel}
          />
        </div>
      ) : null}
    </>
  ) : null;

  const compactSecondaryDrawer = compactViewport && activeSecondarySurface ? (
    <MeetingWorkbenchSecondaryDrawer
      label={activeSecondarySurface === 'inspector'
        ? t('meetingWorkbenchInspectorLabel')
        : activeSecondarySurface === 'console'
          ? t(isConsoleOpen ? 'meetingWorkbenchCollapseConsole' : 'meetingWorkbenchOpenConsole')
          : activeSecondarySurface === 'sessions'
            ? t('meetingWorkbenchSessions')
            : t('meetingWorkbenchObject')}
      surface={activeSecondarySurface}
      onClose={onCloseSecondary}
    >
      {activeSecondarySurface === 'object' ? (
        <div className="flex h-full min-h-0 flex-col bg-white dark:bg-slate-950">
          {graphViewMode === 'work' ? (
            <div className="min-h-0 max-h-[45%] flex-none overflow-auto border-b border-slate-200 dark:border-slate-800">
              <ObjectOutlinerPanel
                graphViewMode={graphViewMode}
                nodes={nodes}
                summary={summary}
                attachResponse={attachResponse}
                selectedNodeId={selectedNodeId}
                activeMissingContext={activeMissingContext}
                onSelectNode={onSelectNodeFromDrawer}
                onSelectMissingContext={onSelectMissingContextFromDrawer}
                presentation="drawer"
                t={t}
              />
            </div>
          ) : null}
          <div className="min-h-0 flex-1 overflow-auto">
            <MeetingObjectContextPanel
              summary={summary}
              selection={selection}
              attachResponse={attachResponse}
              meetingId={activeMeetingId}
              surfaceRoute={surfaceRoute}
              onSwitchObject={onSwitchObject}
              onClose={onCloseInfoPanel}
              presentation="drawer"
            />
          </div>
        </div>
      ) : null}
      {activeSecondarySurface === 'sessions' ? (
        <MeetingSessionsPopover
          sessions={sessions}
          activeMeetingId={activeMeetingId}
          loading={sessionsLoading}
          error={sessionsError}
          creating={creatingSession}
          createError={createSessionError}
          onCreateSession={onCreateSession}
          onRetry={onRetrySessions}
          onSelectSession={onSelectSession}
          onClose={onCloseInfoPanel}
          presentation="drawer"
        />
      ) : null}
      {activeSecondarySurface === 'inspector' ? (
        <MeetingWorkbenchInspectorDock
          {...inspectorDockProps}
          presentation="drawer"
          railPlacement="leading"
        />
      ) : null}
      {activeSecondarySurface === 'console' ? (
        <MeetingConsoleDrawer
          selectedNode={selectedNode}
          onClose={onCloseSecondary}
          presentation="drawer"
        />
      ) : null}
    </MeetingWorkbenchSecondaryDrawer>
  ) : null;

  return { floatingPanel, compactSecondaryDrawer };
}
