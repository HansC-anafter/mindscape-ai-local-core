import React from 'react';

import type {
  AddressableObjectSummary,
  ObjectGraphProjection,
  ObjectMeetingAttachResponse,
} from '@/lib/addressable-object-layer';
import { MeetingInspectorPanel, MeetingInspectorRail } from './PropertiesInspector';
import type {
  GraphViewMode,
  InspectorTab,
  MeetingCommandImpact,
  MeetingEventSummary,
  MeetingNode,
  MeetingTranslate,
  RuntimeInspectorSnapshot,
} from './meetingWorkbenchTypes';

export interface MeetingWorkbenchInspectorDockProps {
  activeInspector: InspectorTab | null;
  graphViewMode: GraphViewMode;
  selectedNode: MeetingNode | null;
  runtimeSnapshot: RuntimeInspectorSnapshot;
  workspaceId: string;
  apiUrl: string;
  capabilityCode: string;
  meetingId: string;
  summary: AddressableObjectSummary | null;
  attachResponse: ObjectMeetingAttachResponse | null;
  surfaceRoute: string;
  objectGraphProjections: ObjectGraphProjection[];
  objectGraphLoading: boolean;
  objectGraphError: string | null;
  commandImpact: MeetingCommandImpact | null;
  traceEvents: MeetingEventSummary[];
  eventCounts: Record<string, number>;
  activeTraceFilter: string | null;
  onTraceFilterChange: (filter: string | null) => void;
  onToggleInspector: (tab: InspectorTab) => void;
  onClose: () => void;
  presentation?: 'inline' | 'drawer';
  railPlacement?: 'leading' | 'trailing';
  t: MeetingTranslate;
}

export function MeetingWorkbenchInspectorDock({
  activeInspector,
  graphViewMode,
  selectedNode,
  runtimeSnapshot,
  workspaceId,
  apiUrl,
  capabilityCode,
  meetingId,
  summary,
  attachResponse,
  surfaceRoute,
  objectGraphProjections,
  objectGraphLoading,
  objectGraphError,
  commandImpact,
  traceEvents,
  eventCounts,
  activeTraceFilter,
  onTraceFilterChange,
  onToggleInspector,
  onClose,
  presentation = 'inline',
  railPlacement = 'trailing',
  t,
}: MeetingWorkbenchInspectorDockProps) {
  if (presentation === 'drawer' && !activeInspector) {
    return null;
  }

  const panel = activeInspector ? (
    <MeetingInspectorPanel
      activeInspector={activeInspector}
      graphViewMode={graphViewMode}
      selectedNode={selectedNode}
      runtimeSnapshot={runtimeSnapshot}
      workspaceId={workspaceId}
      apiUrl={apiUrl}
      capabilityCode={capabilityCode}
      meetingId={meetingId}
      summary={summary}
      attachResponse={attachResponse}
      surfaceRoute={surfaceRoute}
      objectGraphProjections={objectGraphProjections}
      objectGraphLoading={objectGraphLoading}
      objectGraphError={objectGraphError}
      commandImpact={commandImpact}
      traceEvents={traceEvents}
      eventCounts={eventCounts}
      activeTraceFilter={activeTraceFilter}
      onTraceFilterChange={onTraceFilterChange}
      onClose={onClose}
      presentation={presentation}
      t={t}
    />
  ) : null;

  if (presentation === 'drawer') {
    return (
      <div className="flex h-full min-h-0 bg-white dark:bg-slate-950">
        <MeetingInspectorRail
          activeInspector={activeInspector}
          graphViewMode={graphViewMode}
          onToggleInspector={onToggleInspector}
          placement={railPlacement}
          t={t}
        />
        {panel}
      </div>
    );
  }

  return (
    <>
      <MeetingInspectorRail
        activeInspector={activeInspector}
        graphViewMode={graphViewMode}
        onToggleInspector={onToggleInspector}
        placement={railPlacement}
        t={t}
      />
      {panel}
    </>
  );
}
