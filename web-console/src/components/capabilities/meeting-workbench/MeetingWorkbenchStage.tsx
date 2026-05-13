import type { ReactNode } from 'react';

import type { CompositionGraphCommandEnvelopeDraft } from '@/lib/composition-graph';
import { MeetingTaskCanvas } from './SemanticFlowCanvas';
import { CommandLedgerStrip } from './CommandLedgerStrip';
import { ObjectOutlinerPanel } from './ObjectOutlinerPanel';
import type { AddressableObjectSummary, ObjectMeetingAttachResponse } from '@/lib/addressable-object-layer';
import type { GraphViewMode, MeetingCommandImpact, MeetingGraphEdge, MeetingNode, MeetingTranslate } from './meetingWorkbenchTypes';
import type { MeetingMissingContext } from './meetingWorkbenchStatus';

export function MeetingWorkbenchStage({
  apiUrl,
  workspaceId,
  meetingId,
  graphViewMode,
  nodes,
  edges,
  summary,
  attachResponse,
  selectedNodeId,
  activeMissingContext,
  onSelectNode,
  onSelectMissingContext,
  zoom,
  onZoomIn,
  onZoomOut,
  onResetView,
  onWheelZoom,
  commandImpact,
  command,
  selectedPackTool,
  onCommandEnvelope,
  inspectorSlot,
  t,
}: {
  apiUrl: string;
  workspaceId: string;
  meetingId: string | null;
  graphViewMode: GraphViewMode;
  nodes: MeetingNode[];
  edges: MeetingGraphEdge[];
  summary: AddressableObjectSummary | null;
  attachResponse: ObjectMeetingAttachResponse | null;
  selectedNodeId: string;
  activeMissingContext: MeetingMissingContext | null;
  onSelectNode: (nodeId: string) => void;
  onSelectMissingContext: (context: MeetingMissingContext) => void;
  zoom: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onResetView: () => void;
  onWheelZoom: (deltaY: number) => void;
  commandImpact: MeetingCommandImpact | null;
  command: string;
  selectedPackTool: string | null;
  onCommandEnvelope: (envelope: CompositionGraphCommandEnvelopeDraft) => Promise<void>;
  inspectorSlot?: ReactNode;
  t: MeetingTranslate;
}) {
  return (
    <div
      className="flex min-h-0 flex-1 flex-col bg-slate-100 dark:bg-slate-950"
      data-testid="meeting-workbench-stage"
    >
      <div className="flex min-h-0 flex-1" data-testid="meeting-workbench-main-editors">
        <ObjectOutlinerPanel
          graphViewMode={graphViewMode}
          nodes={nodes}
          summary={summary}
          attachResponse={attachResponse}
          selectedNodeId={selectedNodeId}
          activeMissingContext={activeMissingContext}
          onSelectNode={onSelectNode}
          onSelectMissingContext={onSelectMissingContext}
          t={t}
        />
        <MeetingTaskCanvas
          apiUrl={apiUrl}
          workspaceId={workspaceId}
          meetingId={meetingId}
          nodes={nodes}
          edges={edges}
          selectedNodeId={selectedNodeId}
          onSelectNode={onSelectNode}
          zoom={zoom}
          onZoomIn={onZoomIn}
          onZoomOut={onZoomOut}
          onResetView={onResetView}
          onWheelZoom={onWheelZoom}
          commandImpact={commandImpact}
          graphViewMode={graphViewMode}
          command={command}
          selectedPackTool={selectedPackTool}
          onCommandEnvelope={onCommandEnvelope}
          t={t}
        />
        {inspectorSlot}
      </div>
      <CommandLedgerStrip
        graphViewMode={graphViewMode}
        nodes={nodes}
        selectedNodeId={selectedNodeId}
        onSelectNode={onSelectNode}
        t={t}
      />
    </div>
  );
}
