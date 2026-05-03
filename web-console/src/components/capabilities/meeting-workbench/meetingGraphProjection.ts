import {
  formatEventTime,
  formatKind,
  getEventMessage,
  getEventTitle,
  getEventType,
  truncateText,
} from './meetingGraphFormatting';
import type {
  GraphViewMode,
  MeetingArtifactSummary,
  MeetingEventSummary,
  MeetingGraphEdge,
  MeetingGraphProjection,
  MeetingLane,
  MeetingNode,
  MeetingNodeKind,
  MeetingNodeStatus,
} from './meetingWorkbenchTypes';
import { isRecord, readString, shortId } from './meetingWorkbenchUtils';

export { buildCommandImpact, meetingNodeMatchesImpact } from './meetingCommandImpact';
export {
  formatEventTime,
  formatKind,
  getEventMessage,
  getEventTitle,
  getEventType,
  truncateText,
} from './meetingGraphFormatting';
export {
  addressableRefKey,
  buildObjectGraphNodes,
  collectGraphProjectionRefs,
  graphRefLabel,
} from './meetingGraphObjectProjection';
export { coerceExecutionGraphEdge, coerceExecutionGraphNode } from './meetingGraphParsing';

function mergeMeetingNodes(primaryNodes: MeetingNode[], secondaryNodes: MeetingNode[]): MeetingNode[] {
  const seen = new Set<string>();
  const merged: MeetingNode[] = [];
  [...primaryNodes, ...secondaryNodes].forEach((node) => {
    if (seen.has(node.id)) {
      return;
    }
    seen.add(node.id);
    merged.push(node);
  });
  return merged;
}

function hasExecutableActionSignal(event: MeetingEventSummary): boolean {
  const payload = isRecord(event.payload) ? event.payload : {};
  const metadata = isRecord(event.metadata) ? event.metadata : {};
  const candidateKeys = [
    'execution_id',
    'executionId',
    'task_id',
    'taskId',
    'playbook_code',
    'playbookCode',
    'tool_name',
    'toolName',
    'landing_status',
    'landingStatus',
  ];

  return candidateKeys.some((key) => Boolean(readString(payload[key]) || readString(metadata[key])));
}

function countEventsByType(events: MeetingEventSummary[]): Record<string, number> {
  return events.reduce<Record<string, number>>((counts, event) => {
    const type = getEventType(event);
    counts[type] = (counts[type] ?? 0) + 1;
    return counts;
  }, {});
}

function buildGroupNode(
  id: string,
  title: string,
  count: number,
  lane: MeetingLane,
  traceFilter: string,
  eventIds: string[],
  detail: string,
): MeetingNode | null {
  if (count <= 0) {
    return null;
  }

  return {
    id,
    eyebrow: 'Group',
    title: `${title} - ${count}`,
    detail,
    status: 'ready',
    kind: 'group',
    lane,
    childCount: count,
    eventIds,
    traceFilter,
    defaultInspector: 'trace',
    output: JSON.stringify({ trace_filter: traceFilter, count, event_ids: eventIds }, null, 2),
  };
}

function buildMeetingEventNode(event: MeetingEventSummary, mode: GraphViewMode = 'work'): MeetingNode | null {
  const payload = isRecord(event.payload) ? event.payload : {};
  const metadata = isRecord(event.metadata) ? event.metadata : {};
  const actor = readString(event.actor).toLowerCase();
  const eventType = getEventType(event);
  const stage = readString(payload.stage);
  const status = readString(payload.status).toLowerCase();
  const type = readString(payload.type).toLowerCase();
  const message = getEventMessage(event);
  const isError = type === 'error' || metadata.is_error === true || Boolean(readString(payload.error));

  if (eventType === 'action_item') {
    if (!hasExecutableActionSignal(event)) {
      return null;
    }

    return {
      id: `run-${event.id}`,
      eyebrow: 'Run',
      title: truncateText(getEventTitle(event), 72),
      detail: truncateText(`${formatEventTime(event.timestamp)} executable action`, 120),
      status: status === 'completed' || status === 'done' ? 'ready' : 'running',
      kind: 'run',
      lane: 'runs',
      eventIds: [event.id],
      defaultInspector: 'trace',
      traceFilter: 'action_item',
      output: JSON.stringify({ payload, metadata }, null, 2),
    };
  }

  if (stage && mode !== 'runs') {
    return null;
  }

  if (
    eventType === 'agent_turn' ||
    eventType === 'meeting_round' ||
    eventType === 'meeting_start' ||
    eventType === 'meeting_end' ||
    eventType === 'decision_proposal' ||
    eventType === 'decision_final'
  ) {
    return null;
  }

  let eyebrow = 'Event';
  let nodeStatus: MeetingNodeStatus = 'ready';
  let kind: MeetingNodeKind = 'run';
  let lane: MeetingLane = 'runs';
  if (isError) {
    eyebrow = 'Error';
    nodeStatus = 'error';
  } else if (stage) {
    eyebrow = 'Stage';
    nodeStatus = status === 'completed' || status === 'done' ? 'ready' : 'running';
    kind = 'run';
    lane = 'runs';
  } else if (actor === 'user') {
    eyebrow = 'Command';
    nodeStatus = 'pending';
    kind = 'command';
    lane = 'commands';
  } else if (actor === 'assistant') {
    eyebrow = 'Result';
    nodeStatus = 'ready';
    kind = 'result';
    lane = 'outputs';
  } else {
    return null;
  }

  const titleSource = stage ? formatKind(stage) : message || readString(event.event_type) || shortId(event.id);
  const detailSource = stage && message ? message : `${formatEventTime(event.timestamp)} ${readString(event.event_type)}`.trim();
  const output = message || JSON.stringify({ payload, metadata }, null, 2);

  return {
    id: `${kind}-${event.id}`,
    eyebrow,
    title: truncateText(titleSource, 72),
    detail: truncateText(detailSource || shortId(event.id), 120),
    status: nodeStatus,
    kind,
    lane,
    eventIds: [event.id],
    defaultInspector: stage || kind === 'command' ? 'trace' : undefined,
    traceFilter: stage ? eventType : undefined,
    output,
  };
}

function getArtifactOutput(artifact: MeetingArtifactSummary): string {
  const metadata = isRecord(artifact.metadata) ? artifact.metadata : {};
  const content = isRecord(artifact.content) ? artifact.content : {};
  const output = {
    artifact_id: artifact.id,
    execution_id: artifact.execution_id,
    thread_id: artifact.thread_id,
    storage_ref: artifact.storage_ref,
    content,
    metadata,
  };

  return JSON.stringify(output, null, 2);
}

function buildMeetingArtifactNode(artifact: MeetingArtifactSummary): MeetingNode {
  const title = artifact.title || `Artifact ${shortId(artifact.id)}`;
  const detailParts = [
    artifact.playbook_code || 'artifact',
    artifact.artifact_type,
    artifact.execution_id ? `exec ${shortId(artifact.execution_id)}` : '',
    formatEventTime(artifact.created_at || undefined),
  ].filter(Boolean);

  return {
    id: `artifact-${artifact.id}`,
    eyebrow: 'Artifact',
    title: truncateText(title, 72),
    detail: truncateText(artifact.summary || detailParts.join(' · ') || shortId(artifact.id), 120),
    status: 'ready',
    kind: 'artifact',
    lane: 'artifacts',
    output: getArtifactOutput(artifact),
  };
}

export function projectMeetingGraph({
  activeMeetingId,
  objectKind,
  objectTitle,
  objectDetail,
  events,
  artifacts,
  localTasks,
  objectGraphNodes,
  artifactsLoading,
  artifactsError,
  eventsLoading,
  eventsError,
  executionGraphNodes,
  executionGraphEdges,
  executionGraphLoading,
  executionGraphError,
  mode,
}: {
  activeMeetingId: string;
  objectKind: string;
  objectTitle: string;
  objectDetail: string;
  events: MeetingEventSummary[];
  artifacts: MeetingArtifactSummary[];
  localTasks: MeetingNode[];
  objectGraphNodes: MeetingNode[];
  artifactsLoading: boolean;
  artifactsError: string | null;
  eventsLoading: boolean;
  eventsError: string | null;
  executionGraphNodes: MeetingNode[];
  executionGraphEdges: MeetingGraphEdge[];
  executionGraphLoading: boolean;
  executionGraphError: string | null;
  mode: GraphViewMode;
}): MeetingGraphProjection {
  const eventCounts = countEventsByType(events);
  const actionItemEvents = events.filter((event) => getEventType(event) === 'action_item');
  const executableActionItemEvents = actionItemEvents.filter(hasExecutableActionSignal);
  const collapsedActionItemEvents = actionItemEvents.filter((event) => !hasExecutableActionSignal(event));
  const decisionEvents = events.filter((event) => getEventType(event).startsWith('decision_'));
  const projectedEvents = events
    .map((event) => buildMeetingEventNode(event, mode))
    .filter((node): node is MeetingNode => Boolean(node));

  const groupNodes = [
    buildGroupNode(
      'group-action-items',
      'Action Items',
      collapsedActionItemEvents.length,
      'runs',
      'action_item',
      collapsedActionItemEvents.map((event) => event.id),
      'Collapsed governance action items. Open Trace to inspect raw replay.',
    ),
    buildGroupNode(
      'group-decisions',
      'Decisions',
      decisionEvents.length,
      'outputs',
      'decision',
      decisionEvents.map((event) => event.id),
      'Collapsed decision proposal and finalization events.',
    ),
  ].filter((node): node is MeetingNode => Boolean(node));

  const artifactNodes = artifacts.map(buildMeetingArtifactNode);
  const stateNodes: MeetingNode[] = [];

  if (artifactsLoading || artifactsError) {
    stateNodes.push({
      id: 'artifacts-state',
      eyebrow: artifactsLoading ? 'Artifacts' : 'Artifacts error',
      title: artifactsLoading ? 'Loading artifacts' : 'Artifacts unavailable',
      detail: artifactsLoading
        ? 'Reading landed assets and task results for this meeting.'
        : artifactsError || 'Failed to load meeting artifacts.',
      status: artifactsLoading ? 'running' : 'error',
      kind: 'group',
      lane: 'artifacts',
      defaultInspector: 'trace',
    });
  }

  if (eventsLoading || eventsError) {
    stateNodes.push({
      id: 'events-state',
      eyebrow: eventsLoading ? 'Events' : 'Events error',
      title: eventsLoading ? 'Loading session events' : 'Session events unavailable',
      detail: eventsLoading
        ? 'Reading command, execution, and output history for this meeting.'
        : eventsError || 'Failed to load meeting history.',
      status: eventsLoading ? 'running' : 'error',
      kind: 'group',
      lane: 'runs',
      defaultInspector: 'trace',
    });
  }

  if (executionGraphLoading || executionGraphError) {
    stateNodes.push({
      id: 'execution-graph-state',
      eyebrow: executionGraphLoading ? 'Execution graph' : 'Execution graph error',
      title: executionGraphLoading ? 'Loading execution graph' : 'Execution graph unavailable',
      detail: executionGraphLoading
        ? 'Reading object action plans, runtime closure, and output object proof.'
        : executionGraphError || 'Failed to load execution graph.',
      status: executionGraphLoading ? 'running' : 'error',
      kind: 'group',
      lane: 'runs',
      defaultInspector: 'trace',
    });
  }

  const baseNodes: MeetingNode[] = [
    {
      id: 'root',
      eyebrow: 'Meeting',
      title: shortId(activeMeetingId),
      detail: 'Session root',
      status: 'ready',
      kind: 'meeting',
      lane: 'context',
    },
    {
      id: 'object',
      eyebrow: objectKind,
      title: objectTitle,
      detail: objectDetail,
      status: 'context',
      kind: 'object',
      lane: 'context',
    },
    ...projectedEvents,
    ...objectGraphNodes,
    ...groupNodes,
    ...artifactNodes,
    ...executionGraphNodes,
    ...stateNodes,
    ...localTasks,
    {
      id: 'ready',
      eyebrow: 'Next',
      title: 'Ready for instruction',
      detail: 'Create the next task from the command bar.',
      status: 'pending',
      kind: 'next',
      lane: 'next',
    },
  ];
  const nodes = mergeMeetingNodes(baseNodes, []);

  return {
    nodes,
    edges: executionGraphEdges,
    traceEvents: events,
    eventCounts: {
      ...eventCounts,
      executable_action_item: executableActionItemEvents.length,
      collapsed_action_item: collapsedActionItemEvents.length,
    },
    traceCount: events.length,
    primaryCount: nodes.length,
  };
}
