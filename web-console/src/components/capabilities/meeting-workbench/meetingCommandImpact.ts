import { getEventType } from './meetingGraphFormatting';
import type {
  MeetingCommandImpact,
  MeetingEventSummary,
  MeetingGraphEdge,
  MeetingNode,
  MeetingNodeStatus,
} from './meetingWorkbenchTypes';
import { readString, safeMentionId } from './meetingWorkbenchUtils';

function graphEventNodeId(eventId: string): string {
  return `event-${safeMentionId(eventId)}`;
}

function meetingNodeImpactIds(node: MeetingNode): string[] {
  const ids = new Set<string>([node.id]);
  (node.eventIds || []).forEach((eventId) => ids.add(graphEventNodeId(eventId)));
  if (node.kind === 'command' && node.id.startsWith('command-')) {
    ids.add(`event-${node.id.slice('command-'.length)}`);
  }
  return Array.from(ids);
}

export function meetingNodeMatchesImpact(node: MeetingNode, impactNodeIds: Set<string>): boolean {
  return meetingNodeImpactIds(node).some((id) => impactNodeIds.has(id));
}

function collectCommandImpactNodeIds(commandNode: MeetingNode, edges: MeetingGraphEdge[]): Set<string> {
  const impactNodeIds = new Set<string>(meetingNodeImpactIds(commandNode));
  const pending = Array.from(impactNodeIds);
  const outgoing = new Map<string, MeetingGraphEdge[]>();
  edges.forEach((edge) => {
    const current = outgoing.get(edge.from_id) || [];
    current.push(edge);
    outgoing.set(edge.from_id, current);
  });

  while (pending.length > 0) {
    const nodeId = pending.shift();
    if (!nodeId) {
      continue;
    }
    (outgoing.get(nodeId) || []).forEach((edge) => {
      if (!impactNodeIds.has(edge.to_id)) {
        impactNodeIds.add(edge.to_id);
        pending.push(edge.to_id);
      }
    });
  }

  return impactNodeIds;
}

function addTraceOrderFallbackImpact(
  impactNodeIds: Set<string>,
  commandNode: MeetingNode,
  traceEvents: MeetingEventSummary[],
): void {
  const commandEventId = commandNode.eventIds?.[0];
  if (!commandEventId || impactNodeIds.size > meetingNodeImpactIds(commandNode).length) {
    return;
  }

  const startIndex = traceEvents.findIndex((event) => event.id === commandEventId);
  if (startIndex < 0) {
    return;
  }

  for (let index = startIndex; index < traceEvents.length; index += 1) {
    const event = traceEvents[index];
    if (index > startIndex && readString(event.actor).toLowerCase() === 'user') {
      break;
    }
    impactNodeIds.add(graphEventNodeId(event.id));
  }
}

function deriveCommandImpactStatus(relatedNodes: MeetingNode[], commandNode: MeetingNode): MeetingNodeStatus {
  if (relatedNodes.some((node) => node.status === 'error' || node.status === 'blocked')) {
    return 'error';
  }
  if (relatedNodes.some((node) => node.status === 'running')) {
    return 'running';
  }
  if (relatedNodes.some((node) => node.lane === 'outputs' || node.lane === 'artifacts')) {
    return 'ready';
  }
  return commandNode.status;
}

export function buildCommandImpact(
  commandNode: MeetingNode | null,
  nodes: MeetingNode[],
  edges: MeetingGraphEdge[],
  traceEvents: MeetingEventSummary[],
): MeetingCommandImpact | null {
  if (!commandNode || commandNode.kind !== 'command') {
    return null;
  }

  const impactNodeIds = collectCommandImpactNodeIds(commandNode, edges);
  addTraceOrderFallbackImpact(impactNodeIds, commandNode, traceEvents);
  const relatedNodes = nodes.filter((node) => meetingNodeMatchesImpact(node, impactNodeIds));
  const relatedEvents = traceEvents.filter((event) => impactNodeIds.has(graphEventNodeId(event.id)));
  const edgeIds = new Set(
    edges
      .filter((edge) => impactNodeIds.has(edge.from_id) && impactNodeIds.has(edge.to_id))
      .map((edge) => edge.id),
  );
  const commandNodes = nodes.filter((node) => node.kind === 'command');
  const commandIndex = Math.max(0, commandNodes.findIndex((node) => node.id === commandNode.id));
  const commandText = commandNode.output || commandNode.title;

  return {
    commandNode,
    commandText,
    phase: commandIndex === 0 ? 'initial' : commandIndex === 1 ? 'inserted' : 'follow-up',
    status: deriveCommandImpactStatus(relatedNodes, commandNode),
    nodeIds: impactNodeIds,
    edgeIds,
    relatedNodes,
    relatedEvents,
    decisions: relatedEvents.filter((event) => getEventType(event).startsWith('decision_')),
    actionItems: relatedEvents.filter((event) => getEventType(event) === 'action_item'),
    outputs: relatedNodes.filter((node) => node.lane === 'outputs'),
    artifacts: relatedNodes.filter((node) => node.lane === 'artifacts'),
  };
}
