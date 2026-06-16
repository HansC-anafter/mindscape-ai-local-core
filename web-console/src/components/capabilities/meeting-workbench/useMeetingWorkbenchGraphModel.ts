import { useMemo } from 'react';

import type { AddressableObjectRole, AddressableObjectSummary, ObjectMeetingAttachResponse } from '@/lib/addressable-object-layer';
import { buildCommandImpact, projectMeetingGraph } from './meetingGraphProjection';
import {
  getMeetingFocusRole,
  getMeetingMissingContext,
  getMeetingNextStepNodeId,
  getMeetingNextStepTitle,
  getMeetingRuntimeLabel,
  getMeetingWorkStatus,
  type MeetingMissingContext,
} from './meetingWorkbenchStatus';
import type {
  GraphViewMode,
  MeetingArtifactSummary,
  MeetingEventSummary,
  MeetingGraphEdge,
  MeetingNode,
  MeetingTranslate,
  RuntimeInspectorSnapshot,
} from './meetingWorkbenchTypes';

function getMeetingRoleLabel(role: AddressableObjectRole | null, t: MeetingTranslate): string | null {
  if (role === 'target') {
    return t('meetingWorkbenchRoleTarget');
  }
  if (role === 'evidence') {
    return t('meetingWorkbenchRoleEvidence');
  }
  if (role === 'constraint') {
    return t('meetingWorkbenchRoleConstraint');
  }
  if (role === 'baseline') {
    return t('meetingWorkbenchRoleBaseline');
  }
  if (role === 'source') {
    return t('meetingWorkbenchRoleSource');
  }
  return null;
}

function getMissingContextLabel(context: MeetingMissingContext | null, t: MeetingTranslate): string | null {
  if (context === 'target') {
    return t('meetingWorkbenchRoleTarget');
  }
  return null;
}

export function useMeetingWorkbenchGraphModel({
  activeMeetingId,
  objectKind,
  objectTitle,
  effectiveSummary,
  effectiveAttachResponse,
  hasObjectContext,
  meetingEvents,
  meetingArtifacts,
  localTasks,
  objectGraphNodes,
  meetingArtifactsLoading,
  meetingArtifactsError,
  meetingEventsLoading,
  meetingEventsError,
  executionGraphNodes,
  executionGraphEdges,
  executionGraphLoading,
  executionGraphError,
  graphViewMode,
  selectedNodeId,
  runtimeSnapshot,
  command,
  t,
}: {
  activeMeetingId: string;
  objectKind: string;
  objectTitle: string;
  effectiveSummary: AddressableObjectSummary | null;
  effectiveAttachResponse: ObjectMeetingAttachResponse | null;
  hasObjectContext: boolean;
  meetingEvents: MeetingEventSummary[];
  meetingArtifacts: MeetingArtifactSummary[];
  localTasks: MeetingNode[];
  objectGraphNodes: MeetingNode[];
  meetingArtifactsLoading: boolean;
  meetingArtifactsError: string | null;
  meetingEventsLoading: boolean;
  meetingEventsError: string | null;
  executionGraphNodes: MeetingNode[];
  executionGraphEdges: MeetingGraphEdge[];
  executionGraphLoading: boolean;
  executionGraphError: string | null;
  graphViewMode: GraphViewMode;
  selectedNodeId: string;
  runtimeSnapshot: RuntimeInspectorSnapshot;
  command: string;
  t: MeetingTranslate;
}) {
  const graphProjection = useMemo(
    () => projectMeetingGraph({
      activeMeetingId,
      objectKind,
      objectTitle,
      objectDetail: effectiveSummary?.summary_text || 'Owner-backed object context is attached.',
      events: meetingEvents,
      artifacts: meetingArtifacts,
      localTasks,
      objectGraphNodes,
      artifactsLoading: meetingArtifactsLoading,
      artifactsError: meetingArtifactsError,
      eventsLoading: meetingEventsLoading,
      eventsError: meetingEventsError,
      executionGraphNodes,
      executionGraphEdges,
      executionGraphLoading,
      executionGraphError,
      mode: graphViewMode,
    }),
    [
      activeMeetingId,
      effectiveSummary?.summary_text,
      executionGraphEdges,
      executionGraphError,
      executionGraphLoading,
      executionGraphNodes,
      graphViewMode,
      localTasks,
      meetingArtifacts,
      meetingArtifactsError,
      meetingArtifactsLoading,
      meetingEvents,
      meetingEventsError,
      meetingEventsLoading,
      objectGraphNodes,
      objectKind,
      objectTitle,
    ],
  );
  const nodes = graphProjection.nodes;
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? nodes[0] ?? null;
  const activeWorkStatus = useMemo(() => getMeetingWorkStatus(nodes, command), [command, nodes]);
  const nextStepTitle = useMemo(() => getMeetingNextStepTitle(nodes), [nodes]);
  const nextStepNodeId = useMemo(() => getMeetingNextStepNodeId(nodes), [nodes]);
  const runtimeLabel = useMemo(() => getMeetingRuntimeLabel(runtimeSnapshot), [runtimeSnapshot]);
  const missingContext = useMemo(
    () => hasObjectContext ? getMeetingMissingContext(nodes, effectiveAttachResponse) : null,
    [effectiveAttachResponse, hasObjectContext, nodes],
  );
  const focusRoleLabel = useMemo(
    () => getMeetingRoleLabel(getMeetingFocusRole(effectiveSummary, effectiveAttachResponse), t),
    [effectiveAttachResponse, effectiveSummary, t],
  );
  const missingContextLabel = useMemo(
    () => getMissingContextLabel(missingContext, t),
    [missingContext, t],
  );
  const selectedCommandImpact = useMemo(
    () => buildCommandImpact(selectedNode, nodes, graphProjection.edges, graphProjection.traceEvents),
    [graphProjection.edges, graphProjection.traceEvents, nodes, selectedNode],
  );

  return {
    graphProjection,
    nodes,
    selectedNode,
    activeWorkStatus,
    nextStepTitle,
    nextStepNodeId,
    runtimeLabel,
    missingContext,
    focusRoleLabel,
    missingContextLabel,
    selectedCommandImpact,
  };
}
