import type {
  InspectorTab,
  MeetingGraphEdge,
  MeetingLane,
  MeetingNode,
  MeetingNodeKind,
  MeetingNodeStatus,
} from './meetingWorkbenchTypes';
import { isRecord, readString } from './meetingWorkbenchUtils';

function isMeetingNodeStatus(value: string): value is MeetingNodeStatus {
  return ['ready', 'context', 'pending', 'running', 'blocked', 'error'].includes(value);
}

function normalizeMeetingNodeStatus(value: string): MeetingNodeStatus | null {
  const normalizedValue = value.toLowerCase();
  if (isMeetingNodeStatus(normalizedValue)) {
    return normalizedValue;
  }

  switch (normalizedValue) {
    case 'drafted':
    case 'accepted':
      return 'pending';
    case 'completed':
      return 'ready';
    case 'failed':
      return 'error';
    case 'superseded':
      return 'blocked';
    default:
      return null;
  }
}

function isMeetingNodeKind(value: string): value is MeetingNodeKind {
  return [
    'meeting',
    'object',
    'command',
    'run',
    'runner_task',
    'planner_contract_binding',
    'tool_call',
    'approval_gate',
    'tool_result',
    'object_read',
    'object_write',
    'result',
    'artifact',
    'group',
    'next',
    'event',
  ].includes(value);
}

function isMeetingLane(value: string): value is MeetingLane {
  return ['context', 'graph', 'commands', 'runs', 'outputs', 'artifacts', 'next'].includes(value);
}

function isInspectorTab(value: string): value is InspectorTab {
  return ['object', 'runtime', 'session', 'trace', 'prompts', 'patch', 'graph'].includes(value);
}

export function coerceExecutionGraphNode(rawNode: unknown): MeetingNode | null {
  if (!isRecord(rawNode)) {
    return null;
  }

  const id = readString(rawNode.id);
  const title = readString(rawNode.title);
  const eyebrow = readString(rawNode.eyebrow);
  const status = readString(rawNode.status);
  const kind = readString(rawNode.kind);
  const lane = readString(rawNode.lane);
  const normalizedStatus = normalizeMeetingNodeStatus(status);
  if (!id || !title || !normalizedStatus || !isMeetingNodeKind(kind) || !isMeetingLane(lane)) {
    return null;
  }

  const defaultInspector = readString(rawNode.defaultInspector);
  const childCount = typeof rawNode.childCount === 'number' ? rawNode.childCount : undefined;
  const metadata = isRecord(rawNode.metadata) ? rawNode.metadata : undefined;
  return {
    id,
    title,
    eyebrow: eyebrow || kind,
    detail: readString(rawNode.detail),
    status: normalizedStatus,
    kind,
    lane,
    output: readString(rawNode.output) || undefined,
    childCount,
    defaultInspector: isInspectorTab(defaultInspector) ? defaultInspector : undefined,
    traceFilter: readString(rawNode.traceFilter) || undefined,
    metadata,
  };
}

export function coerceExecutionGraphEdge(rawEdge: unknown): MeetingGraphEdge | null {
  if (!isRecord(rawEdge)) {
    return null;
  }

  const id = readString(rawEdge.id);
  const fromId = readString(rawEdge.from_id);
  const toId = readString(rawEdge.to_id);
  const type = readString(rawEdge.type);
  if (!id || !fromId || !toId || !type) {
    return null;
  }

  return {
    id,
    from_id: fromId,
    to_id: toId,
    type,
    label: readString(rawEdge.label) || null,
    metadata: isRecord(rawEdge.metadata) ? rawEdge.metadata : undefined,
  };
}
