import type {
  AddressableObjectRef,
  AddressableObjectSummary,
  AddressableSelectionTarget,
  ObjectMeetingAttachResponse,
} from '@/lib/addressable-object-layer';
import type { MessageKey } from '@/lib/i18n';

export type InspectorTab = 'object' | 'runtime' | 'session' | 'trace' | 'prompts' | 'patch' | 'graph';
export type MeetingTranslate = (key: MessageKey, params?: Record<string, string>) => string;
export type MeetingNodeStatus = 'ready' | 'context' | 'pending' | 'running' | 'blocked' | 'error';
export type MeetingNodeKind =
  | 'meeting'
  | 'object'
  | 'command'
  | 'run'
  | 'runner_task'
  | 'planner_contract_binding'
  | 'tool_call'
  | 'approval_gate'
  | 'tool_result'
  | 'object_read'
  | 'object_write'
  | 'result'
  | 'artifact'
  | 'group'
  | 'next'
  | 'event';
export type MeetingLane = 'context' | 'graph' | 'commands' | 'runs' | 'outputs' | 'artifacts' | 'next';
export type GraphViewMode = 'work' | 'runs' | 'trace' | 'director';

export interface MeetingNode {
  id: string;
  title: string;
  eyebrow: string;
  detail: string;
  status: MeetingNodeStatus;
  kind: MeetingNodeKind;
  lane: MeetingLane;
  output?: string;
  eventIds?: string[];
  childCount?: number;
  defaultInspector?: InspectorTab;
  traceFilter?: string;
  metadata?: Record<string, unknown>;
}

export interface MeetingGraphEdge {
  id: string;
  from_id: string;
  to_id: string;
  type: string;
  label?: string | null;
  metadata?: Record<string, unknown>;
}

export interface MeetingCommandImpact {
  commandNode: MeetingNode;
  commandText: string;
  phase: 'initial' | 'inserted' | 'follow-up';
  status: MeetingNodeStatus;
  nodeIds: Set<string>;
  edgeIds: Set<string>;
  relatedNodes: MeetingNode[];
  relatedEvents: MeetingEventSummary[];
  decisions: MeetingEventSummary[];
  actionItems: MeetingEventSummary[];
  outputs: MeetingNode[];
  artifacts: MeetingNode[];
}

export interface AgentInfo {
  id: string;
  name: string;
  status: string;
  description?: string;
  transport?: string | null;
  reason?: string | null;
}

export interface RuntimeInspectorSnapshot {
  resolvedRuntime: string | null;
  dispatchChain: string[];
  boundRuntimeIds: string[];
  agents: AgentInfo[];
  loading: boolean;
  error: string | null;
}

export interface MeetingSessionSummary {
  id: string;
  workspace_id?: string;
  started_at?: string;
  is_active?: boolean;
  status?: string;
  meeting_type?: string;
  agenda?: string[];
  metadata?: Record<string, unknown>;
}

export interface MeetingEventSummary {
  id: string;
  timestamp?: string;
  actor?: string;
  event_type?: string;
  payload?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

export interface MeetingArtifactSummary {
  id: string;
  thread_id?: string | null;
  task_id?: string | null;
  execution_id?: string | null;
  playbook_code?: string;
  artifact_type?: string;
  title?: string;
  summary?: string | null;
  content?: Record<string, unknown>;
  storage_ref?: string | null;
  metadata?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface MeetingPackTool {
  id: string;
  label: string;
  description: string;
  capabilityCode: string | null;
  requiredTools: string[];
}

export type MeetingMentionKind =
  | 'object'
  | 'session'
  | 'pack'
  | 'node'
  | 'storyboard'
  | 'scene'
  | 'character';

export type MeetingObjectActionRole =
  | 'source'
  | 'target'
  | 'character'
  | 'constraint'
  | 'baseline'
  | 'evidence';

export interface MeetingObjectActionEntry {
  role: MeetingObjectActionRole;
  ref: AddressableObjectRef;
}

export interface MeetingMentionReference {
  id: string;
  kind: MeetingMentionKind;
  token: string;
  label: string;
  description: string;
  uri?: string;
  ownerPack?: string;
  objectKind?: string;
  capabilityCode?: string;
  sessionId?: string;
  sceneId?: string;
  packageId?: string;
  characterCardId?: string;
  metadata?: Record<string, unknown>;
}

export interface MeetingMentionItem {
  id: string;
  kind: MeetingMentionKind;
  label: string;
  token: string;
  description: string;
  packToolId?: string;
  searchText?: string;
  ref?: MeetingMentionReference;
}

export interface MeetingGraphProjection {
  nodes: MeetingNode[];
  edges: MeetingGraphEdge[];
  traceEvents: MeetingEventSummary[];
  eventCounts: Record<string, number>;
  traceCount: number;
  primaryCount: number;
}

export interface MeetingExecutionGraphPayload {
  nodes?: unknown;
  edges?: unknown;
  task_count?: number;
  relation_count?: number;
  artifact_count?: number;
}

export interface MeetingGraphLaneConfig {
  id: MeetingLane;
  label: string;
  description: string;
}

export interface AOLMeetingBottomShellProps {
  workspaceId: string;
  apiUrl: string;
  capabilityCode?: string;
  meetingId: string | null;
  summary: AddressableObjectSummary | null;
  selection: AddressableSelectionTarget | null;
  attachResponse: ObjectMeetingAttachResponse | null;
  surfaceRoute: string;
  onSwitchObject: () => void;
}

export type MeetingInfoPanel = 'object' | 'sessions';
