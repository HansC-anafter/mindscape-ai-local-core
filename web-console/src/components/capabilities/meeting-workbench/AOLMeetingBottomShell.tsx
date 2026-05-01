'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Box,
  Cpu,
  FileText,
  GitBranch,
  ListTree,
  MessageSquare,
  MousePointer2,
  RotateCcw,
  Send,
  Wrench,
  X,
  ZoomIn,
  ZoomOut,
  type LucideIcon,
} from 'lucide-react';

import { projectAddressableObjectGraph } from '@/lib/addressable-object-layer';
import type {
  AddressableObjectRef,
  AddressableObjectSummary,
  AddressableSelectionTarget,
  ObjectMeetingAttachResponse,
  ObjectGraphProjection,
} from '@/lib/addressable-object-layer';
import { useT } from '@/lib/i18n';
import { useSendMessage } from '@/hooks/useSendMessage';

type InspectorTab = 'object' | 'runtime' | 'session' | 'trace' | 'prompts' | 'patch' | 'graph';
type MeetingNodeStatus = 'ready' | 'context' | 'pending' | 'running' | 'blocked' | 'error';
type MeetingNodeKind = 'meeting' | 'object' | 'command' | 'run' | 'result' | 'artifact' | 'group' | 'next' | 'event';
type MeetingLane = 'context' | 'graph' | 'commands' | 'runs' | 'outputs' | 'artifacts' | 'next';
type GraphViewMode = 'flow' | 'runs' | 'trace';

interface MeetingNode {
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

interface MeetingGraphEdge {
  id: string;
  from_id: string;
  to_id: string;
  type: string;
  label?: string | null;
  metadata?: Record<string, unknown>;
}

interface MeetingCommandImpact {
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

interface AgentInfo {
  id: string;
  name: string;
  status: string;
  description?: string;
  transport?: string | null;
  reason?: string | null;
}

interface RuntimeInspectorSnapshot {
  resolvedRuntime: string | null;
  dispatchChain: string[];
  boundRuntimeIds: string[];
  agents: AgentInfo[];
  loading: boolean;
  error: string | null;
}

interface MeetingSessionSummary {
  id: string;
  workspace_id?: string;
  started_at?: string;
  is_active?: boolean;
  status?: string;
  meeting_type?: string;
  agenda?: string[];
  metadata?: Record<string, unknown>;
}

interface MeetingEventSummary {
  id: string;
  timestamp?: string;
  actor?: string;
  event_type?: string;
  payload?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

interface MeetingArtifactSummary {
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

interface MeetingPackTool {
  id: string;
  label: string;
  description: string;
  capabilityCode: string | null;
  requiredTools: string[];
}

type MeetingMentionKind =
  | 'object'
  | 'session'
  | 'pack'
  | 'node'
  | 'storyboard'
  | 'scene'
  | 'character';

type MeetingObjectActionRole =
  | 'source'
  | 'target'
  | 'character'
  | 'constraint'
  | 'baseline'
  | 'evidence';

interface MeetingObjectActionEntry {
  role: MeetingObjectActionRole;
  ref: AddressableObjectRef;
}

interface MeetingMentionReference {
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

interface MeetingMentionItem {
  id: string;
  kind: MeetingMentionKind;
  label: string;
  token: string;
  description: string;
  packToolId?: string;
  searchText?: string;
  ref?: MeetingMentionReference;
}

interface MeetingGraphProjection {
  nodes: MeetingNode[];
  edges: MeetingGraphEdge[];
  traceEvents: MeetingEventSummary[];
  eventCounts: Record<string, number>;
  traceCount: number;
  primaryCount: number;
}

interface MeetingExecutionGraphPayload {
  nodes?: unknown;
  edges?: unknown;
  task_count?: number;
  relation_count?: number;
  artifact_count?: number;
}

interface MeetingGraphLaneConfig {
  id: MeetingLane;
  label: string;
  description: string;
}

interface AOLMeetingBottomShellProps {
  workspaceId: string;
  apiUrl: string;
  meetingId: string | null;
  summary: AddressableObjectSummary | null;
  selection: AddressableSelectionTarget | null;
  attachResponse: ObjectMeetingAttachResponse | null;
  surfaceRoute: string;
  onSwitchObject: () => void;
}

const INSPECTOR_TABS: Array<{
  id: InspectorTab;
  label: string;
  icon: LucideIcon;
}> = [
  { id: 'object', label: 'Object', icon: Box },
  { id: 'runtime', label: 'Runtime', icon: Cpu },
  { id: 'session', label: 'Session', icon: FileText },
  { id: 'trace', label: 'Trace', icon: ListTree },
  { id: 'graph', label: 'Graph', icon: GitBranch },
  { id: 'prompts', label: 'Prompts', icon: MessageSquare },
  { id: 'patch', label: 'Patch', icon: Wrench },
];

const GRAPH_LANES: MeetingGraphLaneConfig[] = [
  { id: 'context', label: 'Context', description: 'Session and object' },
  { id: 'graph', label: 'Object Graph', description: 'Bounded relations' },
  { id: 'commands', label: 'Commands', description: 'Issued instructions' },
  { id: 'runs', label: 'Runs', description: 'Tools and execution' },
  { id: 'outputs', label: 'Outputs', description: 'Responses' },
  { id: 'artifacts', label: 'Artifacts', description: 'Landed assets' },
  { id: 'next', label: 'Next', description: 'New instruction' },
];

const MIN_CANVAS_ZOOM = 0.7;
const MAX_CANVAS_ZOOM = 1.6;
const CANVAS_ZOOM_STEP = 0.1;
const MIN_DISCRETE_WHEEL_ZOOM_DELTA = 80;
const MENTION_TOKEN_PATTERN = /(^|[\s，,、:：])(@[A-Za-z_][A-Za-z0-9_:-]*)/g;

type MeetingInfoPanel = 'object' | 'sessions';

function shortId(value: string | null | undefined): string {
  if (!value) {
    return 'none';
  }

  if (value.length <= 18) {
    return value;
  }

  return `${value.slice(0, 8)}...${value.slice(-6)}`;
}

function clampCanvasZoom(value: number): number {
  return Math.min(MAX_CANVAS_ZOOM, Math.max(MIN_CANVAS_ZOOM, Number(value.toFixed(2))));
}

function shouldZoomMeetingCanvasFromWheel(event: React.WheelEvent<HTMLElement>): boolean {
  if (event.deltaY === 0 || Math.abs(event.deltaX) > 0) {
    return false;
  }

  const target = event.target as HTMLElement | null;
  if (target?.closest('[data-meeting-node="true"], [data-meeting-lane-scroll="true"]')) {
    return false;
  }

  if (event.deltaMode === 1 || event.deltaMode === 2) {
    return true;
  }

  return Math.abs(event.deltaY) >= MIN_DISCRETE_WHEEL_ZOOM_DELTA && Number.isInteger(event.deltaY);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isMeetingNodeStatus(value: string): value is MeetingNodeStatus {
  return ['ready', 'context', 'pending', 'running', 'blocked', 'error'].includes(value);
}

function isMeetingNodeKind(value: string): value is MeetingNodeKind {
  return ['meeting', 'object', 'command', 'run', 'result', 'artifact', 'group', 'next', 'event'].includes(value);
}

function isMeetingLane(value: string): value is MeetingLane {
  return ['context', 'graph', 'commands', 'runs', 'outputs', 'artifacts', 'next'].includes(value);
}

function isInspectorTab(value: string): value is InspectorTab {
  return ['object', 'runtime', 'session', 'trace', 'prompts', 'patch', 'graph'].includes(value);
}

function readString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function safeMentionId(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, '_');
}

function coerceExecutionGraphNode(rawNode: unknown): MeetingNode | null {
  if (!isRecord(rawNode)) {
    return null;
  }

  const id = readString(rawNode.id);
  const title = readString(rawNode.title);
  const eyebrow = readString(rawNode.eyebrow);
  const status = readString(rawNode.status);
  const kind = readString(rawNode.kind);
  const lane = readString(rawNode.lane);
  if (!id || !title || !isMeetingNodeStatus(status) || !isMeetingNodeKind(kind) || !isMeetingLane(lane)) {
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
    status,
    kind,
    lane,
    output: readString(rawNode.output) || undefined,
    childCount,
    defaultInspector: isInspectorTab(defaultInspector) ? defaultInspector : undefined,
    traceFilter: readString(rawNode.traceFilter) || undefined,
    metadata,
  };
}

function coerceExecutionGraphEdge(rawEdge: unknown): MeetingGraphEdge | null {
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

function addressableRefKey(ref: AddressableObjectRef): string {
  return [ref.uri, ref.owner_pack, ref.object_kind, ref.object_id].filter(Boolean).join('|');
}

function collectGraphProjectionRefs(
  summary: AddressableObjectSummary | null,
  attachResponse: ObjectMeetingAttachResponse | null,
): AddressableObjectRef[] {
  const refs: AddressableObjectRef[] = [];
  const seen = new Set<string>();

  function pushRef(ref: AddressableObjectRef | null | undefined) {
    if (!ref?.owner_pack || !ref.object_kind || !ref.object_id) {
      return;
    }
    const key = addressableRefKey(ref);
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    refs.push(ref);
  }

  pushRef(summary?.ref);
  attachResponse?.attachments.forEach((attachment) => pushRef(attachment.ref));
  attachResponse?.staged_refs.forEach((ref) => pushRef(ref));
  return refs;
}

function graphRefLabel(ref: AddressableObjectRef): string {
  return [ref.owner_pack, ref.object_kind, ref.object_id].filter(Boolean).join(' / ') || ref.uri || 'object';
}

function buildObjectGraphNodes(
  projections: ObjectGraphProjection[],
  loading: boolean,
  error: string | null,
): MeetingNode[] {
  const nodes: MeetingNode[] = projections.map((projection) => {
    const relationCount = projection.relations?.length ?? 0;
    const title = projection.summary?.title || graphRefLabel(projection.ref);
    return {
      id: `object-graph-${safeMentionId(addressableRefKey(projection.ref) || title)}`,
      eyebrow: projection.node_kind || projection.ref.object_kind || 'Object',
      title: truncateText(title, 72),
      detail: `${relationCount} bounded relation${relationCount === 1 ? '' : 's'}`,
      status: relationCount > 0 ? 'ready' : 'context',
      kind: 'object',
      lane: 'graph',
      defaultInspector: 'graph',
      childCount: relationCount || undefined,
      output: JSON.stringify(projection, null, 2),
    };
  });

  if (loading || error) {
    nodes.push({
      id: 'object-graph-state',
      eyebrow: loading ? 'Object graph' : 'Object graph error',
      title: loading ? 'Loading object graph' : 'Object graph unavailable',
      detail: loading
        ? 'Reading bounded owner-pack relation projections.'
        : error || 'Failed to load object graph.',
      status: loading ? 'running' : 'error',
      kind: 'group',
      lane: 'graph',
      defaultInspector: 'graph',
    });
  }

  return nodes;
}

function buildApiUrls(apiUrl: string, path: string): string[] {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const normalizedApiUrl = apiUrl.replace(/\/$/, '');
  const primaryUrl = normalizedApiUrl ? `${normalizedApiUrl}${normalizedPath}` : normalizedPath;
  return primaryUrl === normalizedPath ? [normalizedPath] : [primaryUrl, normalizedPath];
}

async function fetchApiJson(apiUrl: string, path: string): Promise<unknown> {
  let lastError: unknown = null;

  for (const url of buildApiUrls(apiUrl, path)) {
    try {
      const response = await fetch(url, { credentials: 'same-origin' });
      if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError instanceof Error ? lastError : new Error('Request failed');
}

async function postApiJson(
  apiUrl: string,
  path: string,
  body: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<unknown> {
  let lastError: unknown = null;

  for (const url of buildApiUrls(apiUrl, path)) {
    try {
      const response = await fetch(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal,
      });
      if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      lastError = error;
      if (signal?.aborted) {
        throw error;
      }
    }
  }

  throw lastError instanceof Error ? lastError : new Error('Request failed');
}

function createMentionReference(
  item: Omit<MeetingMentionReference, 'description'> & { description?: string },
): MeetingMentionReference {
  return {
    ...item,
    description: item.description || '',
  };
}

function readAolSessionMetadata(session: MeetingSessionSummary | null): Record<string, unknown> | null {
  const metadata = session?.metadata;
  if (!isRecord(metadata)) {
    return null;
  }

  const aolMetadata = metadata.addressable_object_layer;
  return isRecord(aolMetadata) ? aolMetadata : null;
}

function readFirstAolAttachment(session: MeetingSessionSummary | null): Record<string, unknown> | null {
  const aolMetadata = readAolSessionMetadata(session);
  const attachments = aolMetadata?.context_attachments;
  if (!Array.isArray(attachments)) {
    return null;
  }

  return attachments.find(isRecord) ?? null;
}

function readFirstAolContextEntry(session: MeetingSessionSummary | null): Record<string, unknown> | null {
  const aolMetadata = readAolSessionMetadata(session);
  const entries = aolMetadata?.context_entries;
  if (!Array.isArray(entries)) {
    return null;
  }

  return entries.find(isRecord) ?? null;
}

function buildSessionObjectSummary(session: MeetingSessionSummary | null): AddressableObjectSummary | null {
  const attachment = readFirstAolAttachment(session);
  const contextEntry = readFirstAolContextEntry(session);
  const attachmentRef = isRecord(attachment?.object_ref) ? attachment?.object_ref : null;
  const entryRef = isRecord(contextEntry?.ref) ? contextEntry?.ref : null;
  const refSource = attachmentRef ?? entryRef;

  if (!refSource) {
    return null;
  }

  const ownerPack = readString(refSource.owner_pack);
  const objectKind = readString(refSource.object_kind);
  const objectId = readString(refSource.object_id);
  if (!ownerPack || !objectKind || !objectId) {
    return null;
  }

  const objectSummary = isRecord(attachment?.object_summary) ? attachment?.object_summary : null;
  const labels = Array.isArray(objectSummary?.labels)
    ? objectSummary.labels.filter((label): label is string => typeof label === 'string')
    : [];

  return {
    ref: {
      uri: readString(refSource.uri) || `mindscape://${ownerPack}/${objectKind}/${objectId}`,
      owner_pack: ownerPack,
      object_kind: objectKind,
      object_id: objectId,
      workspace_id: readString(refSource.workspace_id) || session?.workspace_id || null,
      version: readString(refSource.version) || null,
      selector: isRecord(refSource.selector) ? refSource.selector : null,
      source_surface: readString(refSource.source_surface) || null,
    },
    title: readString(objectSummary?.title) || objectId,
    subtitle: readString(objectSummary?.subtitle) || null,
    summary_text: readString(objectSummary?.summary_text) || null,
    status: readString(objectSummary?.status) || null,
    labels,
    owner_surface_url: readString(objectSummary?.owner_surface_url) || null,
  };
}

function buildSessionSelection(session: MeetingSessionSummary | null): AddressableSelectionTarget | null {
  const summary = buildSessionObjectSummary(session);
  if (!summary) {
    return null;
  }

  return {
    ownerPack: summary.ref.owner_pack,
    objectKind: summary.ref.object_kind,
    objectId: summary.ref.object_id,
    version: summary.ref.version ?? undefined,
    selector: summary.ref.selector ?? undefined,
    sourceSurface: summary.ref.source_surface ?? undefined,
    label: summary.title,
    role: 'source',
  };
}

function buildSessionAttachResponse(
  session: MeetingSessionSummary | null,
  workspaceId: string,
): ObjectMeetingAttachResponse | null {
  if (!session) {
    return null;
  }

  const aolMetadata = readAolSessionMetadata(session);
  if (!aolMetadata) {
    return null;
  }

  const entries = Array.isArray(aolMetadata.context_entries)
    ? aolMetadata.context_entries.filter(isRecord)
    : [];
  const stagedRefs = Array.isArray(aolMetadata.staged_refs)
    ? aolMetadata.staged_refs.filter(isRecord)
    : [];
  const reviewRoutes = Array.isArray(aolMetadata.review_routes)
    ? aolMetadata.review_routes.filter((route): route is string => typeof route === 'string')
    : [];
  const attachments: ObjectMeetingAttachResponse['attachments'] = [];

  entries.forEach((entry) => {
    const ref = isRecord(entry.ref) ? entry.ref : null;
    const role = readString(entry.role);
    if (!ref || !role) {
      return;
    }
    attachments.push({
      role: role as ObjectMeetingAttachResponse['attachments'][number]['role'],
      ref: {
        uri: readString(ref.uri),
        owner_pack: readString(ref.owner_pack),
        object_kind: readString(ref.object_kind),
        object_id: readString(ref.object_id),
        workspace_id: readString(ref.workspace_id) || session.workspace_id || workspaceId || null,
        version: readString(ref.version) || null,
        selector: isRecord(ref.selector) ? ref.selector : null,
        source_surface: readString(ref.source_surface) || null,
      },
      projection_level: 'meeting',
    });
  });

  return {
    workspace_id: session.workspace_id || workspaceId,
    meeting_id: session.id,
    status: readString(aolMetadata.status) === 'materialized' ? 'materialized' : 'attached',
    attachments,
    target_ref: null,
    staged_refs: stagedRefs.map((ref) => ({
      uri: readString(ref.uri),
      owner_pack: readString(ref.owner_pack),
      object_kind: readString(ref.object_kind),
      object_id: readString(ref.object_id),
      workspace_id: readString(ref.workspace_id) || session.workspace_id || workspaceId || null,
      version: readString(ref.version) || null,
      selector: isRecord(ref.selector) ? ref.selector : null,
      source_surface: readString(ref.source_surface) || null,
    })),
    review_routes: reviewRoutes,
    errors: [],
  };
}

function getSessionDisplayTitle(session: MeetingSessionSummary): string {
  const summary = buildSessionObjectSummary(session);
  return summary?.title || session.agenda?.[0] || shortId(session.id);
}

function getSessionSearchCorpus(session: MeetingSessionSummary): string {
  const summary = buildSessionObjectSummary(session);
  const aolMetadata = readAolSessionMetadata(session);
  const parts: string[] = [
    session.id,
    session.status ?? '',
    session.meeting_type ?? '',
    session.started_at ?? '',
    ...(session.agenda ?? []),
    summary?.title ?? '',
    summary?.subtitle ?? '',
    summary?.summary_text ?? '',
    ...(summary?.labels ?? []),
    readString(aolMetadata?.intent_summary),
  ];

  if (session.metadata) {
    try {
      parts.push(JSON.stringify(session.metadata));
    } catch {
      // Ignore non-serializable metadata; API payloads should normally be JSON.
    }
  }

  return parts.join(' ').toLowerCase();
}

function truncateText(value: string, maxLength: number): string {
  const cleaned = value.replace(/\s+/g, ' ').trim();
  if (cleaned.length <= maxLength) {
    return cleaned;
  }

  return `${cleaned.slice(0, Math.max(0, maxLength - 1))}...`;
}

function formatEventTime(value: string | undefined): string {
  if (!value) {
    return '';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString('sv-SE', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function getEventMessage(event: MeetingEventSummary): string {
  const payload = isRecord(event.payload) ? event.payload : {};
  const metadata = isRecord(event.metadata) ? event.metadata : {};
  return (
    readString(payload.message) ||
    readString(payload.text) ||
    readString(payload.content) ||
    readString(payload.error) ||
    readString(metadata.message) ||
    readString(metadata.error) ||
    ''
  );
}

function getEventType(event: MeetingEventSummary): string {
  return readString(event.event_type).toLowerCase() || 'unknown';
}

function getEventTitle(event: MeetingEventSummary): string {
  const payload = isRecord(event.payload) ? event.payload : {};
  return (
    readString(payload.title) ||
    readString(payload.task) ||
    readString(payload.description) ||
    readString(payload.name) ||
    getEventMessage(event) ||
    readString(event.event_type) ||
    shortId(event.id)
  );
}

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

function meetingNodeMatchesImpact(node: MeetingNode, impactNodeIds: Set<string>): boolean {
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

function buildCommandImpact(
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

function buildMeetingEventNode(event: MeetingEventSummary, mode: GraphViewMode = 'flow'): MeetingNode | null {
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

function projectMeetingGraph({
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

function formatSessionTime(value: string | undefined): string {
  if (!value) {
    return '';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString('sv-SE', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).replace(',', '');
}

function formatKind(value: string | null | undefined): string {
  if (!value) {
    return 'object';
  }

  return value.replace(/_/g, ' ');
}

function statusClass(status: MeetingNodeStatus, isSelected: boolean): string {
  if (isSelected) {
    return 'border-blue-500 bg-blue-50 text-blue-950 shadow-sm dark:border-blue-400 dark:bg-blue-950/40 dark:text-blue-100';
  }

  switch (status) {
    case 'context':
      return 'border-emerald-300 bg-emerald-50 text-emerald-950 dark:border-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-100';
    case 'running':
      return 'border-amber-300 bg-amber-50 text-amber-950 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-100';
    case 'blocked':
    case 'error':
      return 'border-rose-300 bg-rose-50 text-rose-950 dark:border-rose-700 dark:bg-rose-950/30 dark:text-rose-100';
    case 'pending':
    case 'ready':
    default:
      return 'border-slate-200 bg-white text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100';
  }
}

function getMentionQuery(command: string): string | null {
  const match = command.match(/(^|\s)@([^\s@]*)$/);
  return match ? match[2].toLowerCase() : null;
}

function applyMentionToken(command: string, token: string): string {
  return command.replace(/(^|\s)@([^\s@]*)$/, (_match, prefix: string) => `${prefix}${token} `);
}

function commandContainsMentionToken(command: string, token: string): boolean {
  MENTION_TOKEN_PATTERN.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = MENTION_TOKEN_PATTERN.exec(command)) !== null) {
    if (match[2] === token) {
      return true;
    }
  }
  return false;
}

function parseRawMentionToken(token: string): MeetingMentionReference | null {
  const rawIdFor = (prefix: string) => {
    if (!token.startsWith(prefix)) {
      return null;
    }
    const value = token.slice(prefix.length).trim();
    return value || null;
  };

  const objectId = rawIdFor('@object:');
  if (objectId) {
    return createMentionReference({
      id: objectId,
      kind: 'object',
      token,
      label: `Object ${shortId(objectId)}`,
      description: 'Unresolved object token',
      metadata: { source: 'raw_mention_token' },
    });
  }

  const packId = rawIdFor('@pack:');
  if (packId) {
    return createMentionReference({
      id: packId,
      kind: 'pack',
      token,
      label: `Pack ${packId}`,
      description: 'Workspace pack tool',
      capabilityCode: packId.includes('.') ? packId.split('.')[0] : undefined,
      objectKind: 'playbook',
      metadata: { source: 'raw_mention_token' },
    });
  }

  const sessionId = rawIdFor('@session:');
  if (sessionId) {
    return createMentionReference({
      id: sessionId,
      kind: 'session',
      token,
      label: `Session ${shortId(sessionId)}`,
      description: 'Meeting session',
      sessionId,
      metadata: { source: 'raw_mention_token' },
    });
  }

  const nodeId = rawIdFor('@node:');
  if (nodeId) {
    return createMentionReference({
      id: nodeId,
      kind: 'node',
      token,
      label: `Node ${shortId(nodeId)}`,
      description: 'Meeting graph node',
      metadata: { source: 'raw_mention_token' },
    });
  }

  return null;
}

function extractMentionReferences(command: string, items: MeetingMentionItem[]): MeetingMentionReference[] {
  const seen = new Set<string>();
  const refs: MeetingMentionReference[] = [];

  function pushRef(ref: MeetingMentionReference) {
    const key = `${ref.kind}:${ref.id}:${ref.token}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    refs.push(ref);
  }

  items.forEach((item) => {
    if (!item.token || !commandContainsMentionToken(command, item.token)) {
      return;
    }

    const ref =
      item.ref ??
      createMentionReference({
        id: item.id,
        kind: item.kind,
        token: item.token,
        label: item.label,
          description: item.description,
        });

    pushRef(ref);
  });

  MENTION_TOKEN_PATTERN.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = MENTION_TOKEN_PATTERN.exec(command)) !== null) {
    const parsed = parseRawMentionToken(match[2]);
    if (parsed) {
      pushRef(parsed);
    }
  }

  return refs;
}

function mentionReferenceToObjectRef(ref: MeetingMentionReference): AddressableObjectRef | null {
  if (!ref.uri || !ref.ownerPack || !ref.objectKind || !ref.id) {
    return null;
  }

  return {
    uri: ref.uri,
    owner_pack: ref.ownerPack,
    object_kind: ref.objectKind,
    object_id: ref.id,
  };
}

function isStoryboardReference(ref: MeetingMentionReference): boolean {
  return (
    ref.kind === 'storyboard' ||
    Boolean(ref.objectKind?.startsWith('storyboard') && ref.objectKind !== 'storyboard_scene')
  );
}

function isStoryboardSceneReference(ref: MeetingMentionReference): boolean {
  return ref.kind === 'scene' || ref.objectKind === 'storyboard_scene';
}

function isCharacterReference(ref: MeetingMentionReference): boolean {
  return ref.kind === 'character' || Boolean(ref.objectKind?.startsWith('character'));
}

function roleForMentionReference(ref: MeetingMentionReference): MeetingObjectActionRole | null {
  if (isStoryboardReference(ref) || isStoryboardSceneReference(ref)) {
    return 'target';
  }
  if (isCharacterReference(ref)) {
    return 'character';
  }
  if (ref.kind === 'object') {
    return 'source';
  }
  return null;
}

function buildObjectActionPlanEntries(
  selectedObjectRef: AddressableObjectRef | null | undefined,
  mentionRefs: MeetingMentionReference[],
): MeetingObjectActionEntry[] {
  const entries: MeetingObjectActionEntry[] = [];
  const seen = new Set<string>();

  function pushEntry(role: MeetingObjectActionRole, ref: AddressableObjectRef) {
    const key = `${role}:${ref.uri}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    entries.push({ role, ref });
  }

  if (selectedObjectRef?.uri) {
    pushEntry('source', selectedObjectRef);
  }

  mentionRefs.forEach((mentionRef) => {
    const objectRef = mentionReferenceToObjectRef(mentionRef);
    const role = roleForMentionReference(mentionRef);
    if (!objectRef || !role) {
      return;
    }
    pushEntry(role, objectRef);
  });

  return entries;
}

function mentionKindForObject(_ownerPack: string, objectKind: string): MeetingMentionKind {
  if (objectKind === 'storyboard') {
    return 'storyboard';
  }
  if (objectKind === 'storyboard_scene') {
    return 'scene';
  }
  if (objectKind.startsWith('storyboard')) {
    return 'storyboard';
  }
  if (objectKind.startsWith('character')) {
    return 'character';
  }
  return 'object';
}

function buildRegistryMentionItems(rawItems: unknown): MeetingMentionItem[] {
  if (!Array.isArray(rawItems)) {
    return [];
  }

  return rawItems
    .filter(isRecord)
    .map((item): MeetingMentionItem | null => {
      const ref = isRecord(item.ref) ? item.ref : null;
      if (!ref) {
        return null;
      }

      const ownerPack = readString(ref.owner_pack);
      const objectKind = readString(ref.object_kind);
      const objectId = readString(ref.object_id);
      const uri = readString(ref.uri);
      if (!ownerPack || !objectKind || !objectId || !uri) {
        return null;
      }

      const token = readString(item.token) || `@object:${objectId}`;
      const label = readString(item.label) || objectId;
      const description = readString(item.description) || uri;
      const kind = mentionKindForObject(ownerPack, objectKind);
      const metadata = isRecord(item.metadata) ? item.metadata : {};
      const sceneId = objectKind === 'storyboard_scene' ? objectId.split(':').pop() || objectId : undefined;
      const sessionId = objectKind.startsWith('storyboard') ? objectId.split(':')[0] : undefined;

      return {
        id: `registry-${safeMentionId(`${ownerPack}-${objectKind}-${objectId}`)}`,
        kind,
        label,
        token,
        description,
        searchText: [
          label,
          token,
          description,
          uri,
          ownerPack,
          objectKind,
          objectId,
          readString(item.source),
        ].join(' '),
        ref: createMentionReference({
          id: objectId,
          kind,
          token,
          label,
          description,
          uri,
          ownerPack,
          objectKind,
          capabilityCode: ownerPack,
          sessionId,
          sceneId,
          packageId: objectKind === 'character_package' ? objectId : undefined,
          characterCardId: objectKind === 'character_card' ? objectId : undefined,
          metadata,
        }),
      };
    })
    .filter((item): item is MeetingMentionItem => Boolean(item));
}

function MeetingSessionStrip({
  sessions,
  activeMeetingId,
  loading,
  error,
  onSelectSession,
}: {
  sessions: MeetingSessionSummary[];
  activeMeetingId: string;
  loading: boolean;
  error: string | null;
  onSelectSession: (session: MeetingSessionSummary) => void;
}) {
  if (loading && sessions.length === 0) {
    return (
      <div
        className="flex h-10 items-center rounded-md border border-slate-200 bg-white/90 px-3 text-xs text-slate-500 shadow-sm dark:border-slate-800 dark:bg-slate-950/90 dark:text-slate-400"
        data-testid="meeting-session-strip"
      >
        Loading meeting sessions...
      </div>
    );
  }

  if (sessions.length === 0) {
    return error ? (
      <div
        className="flex h-10 items-center rounded-md border border-amber-200 bg-amber-50/95 px-3 text-xs text-amber-700 shadow-sm dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-300"
        data-testid="meeting-session-strip"
      >
        {error}
      </div>
    ) : null;
  }

  return (
    <div
      className="flex max-w-full items-center gap-2 overflow-x-auto rounded-md border border-slate-200 bg-white/95 px-2 py-1.5 shadow-sm dark:border-slate-800 dark:bg-slate-950/95"
      data-testid="meeting-session-strip"
      aria-label="Meeting sessions"
    >
      <div className="shrink-0 px-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
        Sessions
      </div>
      {sessions.map((session) => {
        const isActive = session.id === activeMeetingId;
        return (
          <button
            key={session.id}
            type="button"
            onClick={() => onSelectSession(session)}
            className={`grid min-w-[150px] max-w-[190px] shrink-0 gap-0.5 rounded-md border px-2 py-1.5 text-left transition-colors ${
              isActive
                ? 'border-blue-400 bg-blue-50 text-blue-950 dark:border-blue-700 dark:bg-blue-950/40 dark:text-blue-100'
                : 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800'
            }`}
            aria-pressed={isActive}
            title={session.id}
            data-testid={`meeting-session-card-${session.id}`}
          >
            <span className="truncate text-[11px] font-semibold">{getSessionDisplayTitle(session)}</span>
            <span className="flex items-center justify-between gap-2 text-[10px] uppercase tracking-[0.08em] opacity-70">
              <span className="truncate">{session.status || 'session'}</span>
              <span className="shrink-0">{formatSessionTime(session.started_at)}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

function MeetingObjectContextPanel({
  summary,
  selection,
  attachResponse,
  meetingId,
  surfaceRoute,
  onSwitchObject,
  onClose,
}: Pick<
  AOLMeetingBottomShellProps,
  'summary' | 'selection' | 'attachResponse' | 'meetingId' | 'surfaceRoute' | 'onSwitchObject'
> & {
  onClose: () => void;
}) {
  const ref = summary?.ref ?? null;
  const labels = summary?.labels ?? [];
  const ownerSurfaceUrl = summary?.owner_surface_url || surfaceRoute;
  const sourceSurface = ref?.source_surface || selection?.sourceSurface || 'current surface';
  const hasObjectContext = Boolean(summary || selection || attachResponse);

  return (
    <section
      className="pointer-events-auto flex max-h-full w-full flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-950"
      id="meeting-object-context-panel"
      data-testid="meeting-object-context-panel"
      aria-label="Meeting object context"
    >
      <div className="flex h-10 shrink-0 items-center justify-between border-b border-slate-200 px-3 dark:border-slate-800">
        <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
          Object Context
        </div>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100"
          aria-label="Close object context"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col overflow-auto p-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="mt-1 truncate text-sm font-semibold text-slate-950 dark:text-slate-100">
              {summary?.title || selection?.label || 'Meeting sessions'}
            </h2>
          </div>
          <div className="shrink-0 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1 text-[10px] font-semibold uppercase text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300">
            {hasObjectContext ? 'Attached' : 'Browser'}
          </div>
        </div>

        <dl className="mt-3 grid gap-2 text-xs">
          <div className="min-w-0 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-2 dark:border-slate-800 dark:bg-slate-900/70">
            <dt className="text-[10px] uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
              Meeting
            </dt>
            <dd className="mt-1 truncate font-mono text-slate-800 dark:text-slate-100">{shortId(meetingId)}</dd>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="min-w-0 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-2 dark:border-slate-800 dark:bg-slate-900/70">
              <dt className="text-[10px] uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                Owner
              </dt>
              <dd className="mt-1 truncate font-medium text-slate-800 dark:text-slate-100">
                {ref?.owner_pack || selection?.ownerPack || 'unknown'}
              </dd>
            </div>
            <div className="min-w-0 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-2 dark:border-slate-800 dark:bg-slate-900/70">
              <dt className="text-[10px] uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                Kind
              </dt>
              <dd className="mt-1 truncate font-medium text-slate-800 dark:text-slate-100">
                {formatKind(ref?.object_kind || selection?.objectKind)}
              </dd>
            </div>
          </div>
          <div className="min-w-0 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-2 dark:border-slate-800 dark:bg-slate-900/70">
            <dt className="text-[10px] uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
              Source
            </dt>
            <dd className="mt-1 truncate text-slate-800 dark:text-slate-100">{sourceSurface}</dd>
          </div>
        </dl>

        <div className="mt-3 flex flex-wrap gap-1.5" aria-label="Object labels">
          {labels.slice(0, 5).map((label) => (
            <span
              key={label}
              className="max-w-full truncate rounded-md bg-slate-100 px-2 py-1 text-[11px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300"
            >
              {label}
            </span>
          ))}
          {labels.length === 0 ? (
            <span className="rounded-md bg-slate-100 px-2 py-1 text-[11px] text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              No labels
            </span>
          ) : null}
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
          <div className="rounded-md border border-slate-200 px-2.5 py-2 dark:border-slate-800">
            <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
              Attachments
            </div>
            <div className="mt-1 text-sm font-semibold text-slate-950 dark:text-slate-100">
              {attachResponse?.attachments.length ?? 0}
            </div>
          </div>
          <div className="rounded-md border border-slate-200 px-2.5 py-2 dark:border-slate-800">
            <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
              Review
            </div>
            <div className="mt-1 text-sm font-semibold text-slate-950 dark:text-slate-100">
              {attachResponse?.review_routes.length ?? 0}
            </div>
          </div>
        </div>
      </div>

      <div className="grid shrink-0 gap-2 border-t border-slate-200 p-3 dark:border-slate-800">
        <a
          href={ownerSurfaceUrl}
          className="rounded-md border border-slate-300 px-3 py-2 text-center text-xs font-semibold text-slate-700 transition-colors hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-900"
        >
          Open Owner Surface
        </a>
        <button
          type="button"
          onClick={() => {
            onSwitchObject();
            onClose();
          }}
          className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs font-semibold text-blue-700 transition-colors hover:bg-blue-100 dark:border-blue-900 dark:bg-blue-950/30 dark:text-blue-300 dark:hover:bg-blue-950/60"
        >
          Switch Object
        </button>
      </div>
    </section>
  );
}

function MeetingSessionsPopover({
  sessions,
  activeMeetingId,
  loading,
  error,
  onSelectSession,
  onClose,
}: {
  sessions: MeetingSessionSummary[];
  activeMeetingId: string;
  loading: boolean;
  error: string | null;
  onSelectSession: (session: MeetingSessionSummary) => void;
  onClose: () => void;
}) {
  const [sessionQuery, setSessionQuery] = useState('');
  const normalizedQuery = sessionQuery.trim().toLowerCase();
  const visibleSessions = useMemo(() => {
    if (!normalizedQuery) {
      return sessions.slice(0, 24);
    }

    return sessions.filter((session) => getSessionSearchCorpus(session).includes(normalizedQuery));
  }, [normalizedQuery, sessions]);
  const resultLabel = normalizedQuery
    ? `${visibleSessions.length}/${sessions.length}`
    : `${Math.min(visibleSessions.length, sessions.length)}/${sessions.length}`;

  return (
    <section
      className="pointer-events-auto rounded-lg border border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-950"
      id="meeting-sessions-popover"
      data-testid="meeting-sessions-popover"
      aria-label="Meeting sessions"
    >
      <div className="flex h-10 items-center justify-between border-b border-slate-200 px-3 dark:border-slate-800">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
          <FileText className="h-4 w-4" aria-hidden="true" />
          Sessions
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500 dark:bg-slate-900 dark:text-slate-400">
            {sessions.length}
          </span>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100"
          aria-label="Close meeting sessions"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <div className="p-2">
        <div className="mb-2 flex items-center gap-2">
          <input
            type="search"
            value={sessionQuery}
            onChange={(event) => setSessionQuery(event.target.value)}
            className="h-8 min-w-0 flex-1 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-blue-600 dark:focus:ring-blue-950"
            placeholder="Search session, object, agenda..."
            aria-label="Search meeting sessions"
            data-testid="meeting-session-search"
          />
          <span
            className="shrink-0 rounded bg-slate-100 px-2 py-1 text-[10px] font-semibold text-slate-500 dark:bg-slate-900 dark:text-slate-400"
            data-testid="meeting-session-result-count"
          >
            {resultLabel}
          </span>
        </div>
        {visibleSessions.length > 0 || loading || error ? (
          <MeetingSessionStrip
            sessions={visibleSessions}
            activeMeetingId={activeMeetingId}
            loading={loading}
            error={error}
            onSelectSession={onSelectSession}
          />
        ) : (
          <div
            className="flex h-10 items-center rounded-md border border-slate-200 bg-slate-50 px-3 text-xs text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400"
            data-testid="meeting-session-empty"
          >
            No matching sessions.
          </div>
        )}
      </div>
    </section>
  );
}

function MeetingHeaderToolbar({
  activePanel,
  activeMeetingId,
  sessionsCount,
  sessionsLoading,
  objectTitle,
  hasObjectContext,
  graphViewMode,
  primaryCount,
  traceCount,
  onTogglePanel,
  onGraphViewModeChange,
}: {
  activePanel: MeetingInfoPanel | null;
  activeMeetingId: string;
  sessionsCount: number;
  sessionsLoading: boolean;
  objectTitle: string;
  hasObjectContext: boolean;
  graphViewMode: GraphViewMode;
  primaryCount: number;
  traceCount: number;
  onTogglePanel: (panel: MeetingInfoPanel) => void;
  onGraphViewModeChange: (mode: GraphViewMode) => void;
}) {
  return (
    <header
      className="flex h-11 shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white px-3 dark:border-slate-800 dark:bg-slate-950"
      data-testid="meeting-header-toolbar"
    >
      <div className="flex min-w-0 items-center gap-2">
        <button
          type="button"
          onClick={() => onTogglePanel('object')}
          className={`inline-flex h-8 max-w-[220px] items-center gap-2 rounded-md border px-2.5 text-xs font-semibold transition-colors ${
            activePanel === 'object'
              ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950/40 dark:text-blue-300'
              : 'border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800'
          }`}
          data-testid="meeting-object-context-toggle"
          aria-expanded={activePanel === 'object'}
          aria-controls="meeting-object-context-panel"
        >
          <Box className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="truncate">Object</span>
          <span className="hidden max-w-[110px] truncate text-[11px] font-medium opacity-70 md:inline">
            {hasObjectContext ? objectTitle : 'Browser'}
          </span>
        </button>
        <button
          type="button"
          onClick={() => onTogglePanel('sessions')}
          className={`inline-flex h-8 items-center gap-2 rounded-md border px-2.5 text-xs font-semibold transition-colors ${
            activePanel === 'sessions'
              ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950/40 dark:text-blue-300'
              : 'border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800'
          }`}
          data-testid="meeting-sessions-toggle"
          aria-expanded={activePanel === 'sessions'}
          aria-controls="meeting-sessions-popover"
        >
          <FileText className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>Sessions</span>
          <span className="rounded bg-white px-1.5 py-0.5 text-[10px] tabular-nums text-slate-500 dark:bg-slate-950 dark:text-slate-400">
            {sessionsLoading ? '...' : sessionsCount}
          </span>
        </button>
        <div
          className="hidden items-center overflow-hidden rounded-md border border-slate-200 bg-slate-50 p-0.5 dark:border-slate-800 dark:bg-slate-900 md:flex"
          data-testid="meeting-graph-view-mode"
          aria-label="Meeting graph view mode"
        >
          {(['flow', 'runs', 'trace'] as GraphViewMode[]).map((mode) => {
            const isActive = graphViewMode === mode;
            return (
              <button
                key={mode}
                type="button"
                onClick={() => onGraphViewModeChange(mode)}
                className={`h-7 rounded px-2 text-[11px] font-semibold uppercase tracking-[0.08em] transition-colors ${
                  isActive
                    ? 'bg-white text-blue-700 shadow-sm dark:bg-slate-950 dark:text-blue-300'
                    : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100'
                }`}
                data-testid={`meeting-graph-view-${mode}`}
                aria-pressed={isActive}
              >
                {mode}
              </button>
            );
          })}
        </div>
      </div>
      <div className="hidden min-w-0 items-center gap-2 text-xs text-slate-500 dark:text-slate-400 sm:flex">
        <span className="truncate rounded bg-slate-100 px-2 py-1 font-medium text-slate-600 dark:bg-slate-900 dark:text-slate-300">
          {graphViewMode} - {primaryCount} nodes - {traceCount} trace events
        </span>
        <span className="shrink-0 font-semibold uppercase tracking-[0.12em]">Active</span>
        <span className="truncate font-mono text-slate-700 dark:text-slate-200">{shortId(activeMeetingId)}</span>
      </div>
    </header>
  );
}

function MeetingTaskCanvas({
  nodes,
  selectedNodeId,
  onSelectNode,
  zoom,
  onZoomIn,
  onZoomOut,
  onResetView,
  onWheelZoom,
  commandImpact,
}: {
  nodes: MeetingNode[];
  selectedNodeId: string;
  onSelectNode: (nodeId: string) => void;
  zoom: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onResetView: () => void;
  onWheelZoom: (deltaY: number) => void;
  commandImpact: MeetingCommandImpact | null;
}) {
  const viewportRef = useRef<HTMLElement | null>(null);
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    panX: number;
    panY: number;
  } | null>(null);
  const [isDraggingCanvas, setIsDraggingCanvas] = useState(false);
  const [canvasPan, setCanvasPan] = useState({ x: 0, y: 0 });
  const nodesByLane = useMemo(() => {
    const grouped = new Map<MeetingLane, MeetingNode[]>();
    GRAPH_LANES.forEach((lane) => grouped.set(lane.id, []));
    nodes.forEach((node) => {
      const laneNodes = grouped.get(node.lane) ?? [];
      laneNodes.push(node);
      grouped.set(node.lane, laneNodes);
    });
    return grouped;
  }, [nodes]);
  const commandDisplay = useMemo(() => {
    const display = new Map<string, { sequence: number; phase: MeetingCommandImpact['phase'] }>();
    nodes
      .filter((node) => node.kind === 'command')
      .forEach((node, index) => {
        display.set(node.id, {
          sequence: index + 1,
          phase: index === 0 ? 'initial' : index === 1 ? 'inserted' : 'follow-up',
        });
      });
    return display;
  }, [nodes]);

  return (
    <section
      ref={viewportRef}
      className={`relative min-h-0 flex-1 overflow-auto bg-slate-100/80 px-4 py-3 dark:bg-slate-950/80 ${
        isDraggingCanvas ? 'cursor-grabbing' : 'cursor-grab'
      }`}
      data-testid="meeting-task-canvas"
      aria-label="Meeting task graph"
      onPointerDown={(event) => {
        if ((event.target as HTMLElement).closest('[data-meeting-node="true"], button, input, a')) {
          return;
        }

        dragRef.current = {
          pointerId: event.pointerId,
          startX: event.clientX,
          startY: event.clientY,
          panX: canvasPan.x,
          panY: canvasPan.y,
        };
        setIsDraggingCanvas(true);
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={(event) => {
        const drag = dragRef.current;
        if (!drag || drag.pointerId !== event.pointerId) {
          return;
        }

        setCanvasPan({
          x: drag.panX + event.clientX - drag.startX,
          y: drag.panY + event.clientY - drag.startY,
        });
      }}
      onPointerUp={(event) => {
        if (dragRef.current?.pointerId === event.pointerId) {
          dragRef.current = null;
          setIsDraggingCanvas(false);
          event.currentTarget.releasePointerCapture(event.pointerId);
        }
      }}
      onPointerCancel={(event) => {
        if (dragRef.current?.pointerId === event.pointerId) {
          dragRef.current = null;
          setIsDraggingCanvas(false);
        }
      }}
      onWheel={(event) => {
        if (!shouldZoomMeetingCanvasFromWheel(event)) {
          return;
        }
        event.preventDefault();
        const nextZoom = clampCanvasZoom(zoom + (event.deltaY < 0 ? CANVAS_ZOOM_STEP : -CANVAS_ZOOM_STEP));
        if (nextZoom !== zoom) {
          const rect = event.currentTarget.getBoundingClientRect();
          const anchorX = event.clientX - rect.left;
          const anchorY = event.clientY - rect.top;
          setCanvasPan((current) => ({
            x: anchorX - ((anchorX - current.x) * nextZoom) / zoom,
            y: anchorY - ((anchorY - current.y) * nextZoom) / zoom,
          }));
        }
        onWheelZoom(event.deltaY);
      }}
    >
      <div className="absolute right-3 top-3 z-10 flex items-center gap-1 rounded-md border border-slate-200 bg-white/95 p-1 shadow-sm dark:border-slate-800 dark:bg-slate-950/95">
        <button
          type="button"
          onClick={onZoomOut}
          className="inline-flex h-8 w-8 items-center justify-center rounded text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100"
          data-testid="meeting-canvas-zoom-out"
          aria-label="Zoom out graph"
          title="Zoom out"
        >
          <ZoomOut className="h-4 w-4" aria-hidden="true" />
        </button>
        <div className="min-w-12 text-center text-[11px] font-semibold tabular-nums text-slate-500 dark:text-slate-400">
          {Math.round(zoom * 100)}%
        </div>
        <button
          type="button"
          onClick={onZoomIn}
          className="inline-flex h-8 w-8 items-center justify-center rounded text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100"
          data-testid="meeting-canvas-zoom-in"
          aria-label="Zoom in graph"
          title="Zoom in"
        >
          <ZoomIn className="h-4 w-4" aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={() => {
            setCanvasPan({ x: 0, y: 0 });
            onResetView();
          }}
          className="inline-flex h-8 w-8 items-center justify-center rounded text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100"
          data-testid="meeting-canvas-fit"
          aria-label="Fit graph view"
          title="Fit"
        >
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      <div className="absolute left-3 top-3 z-10 hidden items-center gap-1 rounded-md bg-white/80 px-2 py-1 text-[11px] text-slate-500 shadow-sm dark:bg-slate-950/80 dark:text-slate-400 md:flex">
        <MousePointer2 className="h-3.5 w-3.5" aria-hidden="true" />
        Drag background to pan / mouse wheel zoom
      </div>

      <div className="flex min-h-full items-start justify-center pt-16">
        <div
          className="w-max"
          style={{
            transform: `translate(${canvasPan.x}px, ${canvasPan.y}px) scale(${zoom})`,
            transformOrigin: 'center center',
          }}
          data-testid="meeting-graph-canvas-content"
        >
          <div
            className="grid grid-cols-[repeat(7,minmax(11rem,15rem))] items-start gap-3"
            data-testid="meeting-graph-lanes"
          >
            {GRAPH_LANES.map((lane) => {
              const laneNodes = nodesByLane.get(lane.id) ?? [];
              return (
                <section
                  key={lane.id}
                  className="min-h-[15rem] rounded-lg border border-slate-200 bg-white/80 p-2 shadow-sm dark:border-slate-800 dark:bg-slate-950/80"
                  data-testid={`meeting-graph-lane-${lane.id}`}
                  aria-label={`${lane.label} lane`}
                >
                  <div className="mb-2 flex items-center justify-between gap-2 border-b border-slate-200 pb-2 dark:border-slate-800">
                    <div className="min-w-0">
                      <div className="truncate text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                        {lane.label}
                      </div>
                      <div className="truncate text-[11px] text-slate-400 dark:text-slate-500">
                        {lane.description}
                      </div>
                    </div>
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-slate-500 dark:bg-slate-900 dark:text-slate-400">
                      {laneNodes.length}
                    </span>
                  </div>
                  <div className="max-h-72 space-y-2 overflow-auto pr-1" data-meeting-lane-scroll="true">
                    {laneNodes.length > 0 ? (
                      laneNodes.map((node) => {
                        const isSelected = node.id === selectedNodeId;
                        const isImpactRelated = commandImpact
                          ? meetingNodeMatchesImpact(node, commandImpact.nodeIds)
                          : false;
                        const isImpactMuted = Boolean(commandImpact) && !isImpactRelated;
                        const commandMeta = commandDisplay.get(node.id);
                        return (
                          <button
                            key={node.id}
                            type="button"
                            onClick={() => onSelectNode(node.id)}
                            className={`w-full rounded-md border p-2.5 text-left transition-colors ${statusClass(
                              node.status,
                              isSelected,
                            )} ${
                              isImpactRelated && !isSelected
                                ? 'ring-2 ring-blue-200 dark:ring-blue-800'
                                : ''
                            } ${
                              isImpactMuted
                                ? 'opacity-35'
                                : ''
                            }`}
                            data-testid={`meeting-graph-node-${node.id}`}
                            data-meeting-node="true"
                            data-impact-state={commandImpact ? (isImpactRelated ? 'related' : 'muted') : 'none'}
                            aria-pressed={isSelected}
                          >
                            <div className="flex items-start gap-2">
                              <GitBranch className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                              <span className="truncate text-[10px] font-semibold uppercase tracking-[0.12em] opacity-70">
                                {node.eyebrow}
                              </span>
                              <div className="ml-auto flex max-w-[8.5rem] flex-wrap justify-end gap-1">
                                {commandMeta ? (
                                  <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-200">
                                    #{commandMeta.sequence} {commandMeta.phase}
                                  </span>
                                ) : null}
                                {node.childCount ? (
                                  <span className="rounded bg-white/70 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums opacity-80 dark:bg-slate-950/70">
                                    {node.childCount}
                                  </span>
                                ) : null}
                                {isImpactRelated && !isSelected ? (
                                  <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-blue-700 dark:bg-blue-950/60 dark:text-blue-200">
                                    Impact
                                  </span>
                                ) : null}
                              </div>
                            </div>
                            <div className="mt-2 truncate text-sm font-semibold">{node.title}</div>
                            <div className="mt-1 max-h-10 overflow-hidden text-xs leading-5 opacity-75">
                              {node.detail}
                            </div>
                          </button>
                        );
                      })
                    ) : (
                      <div className="rounded-md border border-dashed border-slate-200 px-2 py-3 text-xs text-slate-400 dark:border-slate-800 dark:text-slate-500">
                        No nodes
                      </div>
                    )}
                  </div>
                </section>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}

function MeetingCommandBar({
  command,
  onCommandChange,
  onSubmitCommand,
  isDispatching,
  isConsoleOpen,
  onToggleConsole,
  packTools,
  selectedPackToolId,
  onSelectedPackToolChange,
  packToolsLoading,
  packToolsError,
  hasActiveMeeting,
  mentionItems,
  mentionItemsLoading,
  mentionItemsError,
  onApplyMention,
}: {
  command: string;
  onCommandChange: (value: string) => void;
  onSubmitCommand: () => void | Promise<void>;
  isDispatching: boolean;
  isConsoleOpen: boolean;
  onToggleConsole: () => void;
  packTools: MeetingPackTool[];
  selectedPackToolId: string;
  onSelectedPackToolChange: (toolId: string) => void;
  packToolsLoading: boolean;
  packToolsError: string | null;
  hasActiveMeeting: boolean;
  mentionItems: MeetingMentionItem[];
  mentionItemsLoading: boolean;
  mentionItemsError: string | null;
  onApplyMention: (item: MeetingMentionItem) => void;
}) {
  const selectedPackTool = packTools.find((tool) => tool.id === selectedPackToolId) ?? null;
  const mentionQuery = getMentionQuery(command);
  const mentionOptions = useMemo(() => {
    if (mentionQuery === null) {
      return [];
    }

    return mentionItems
      .filter((item) => {
        const haystack = `${item.label} ${item.token} ${item.description} ${item.kind} ${
          item.searchText || ''
        }`.toLowerCase();
        return haystack.includes(mentionQuery);
      })
      .slice(0, 8);
  }, [mentionItems, mentionQuery]);
  const showMentionPicker = hasActiveMeeting && mentionQuery !== null;

  const applyMention = (item: MeetingMentionItem) => {
    onCommandChange(applyMentionToken(command, item.token));
    onApplyMention(item);
    if (item.packToolId) {
      onSelectedPackToolChange(item.packToolId);
    }
  };

  return (
    <form
      className="flex shrink-0 items-center gap-2 border-t border-slate-200 bg-white px-3 py-2 dark:border-slate-800 dark:bg-slate-950"
      data-testid="meeting-command-bar"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmitCommand();
      }}
    >
      <button
        type="button"
        onClick={onToggleConsole}
        className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border transition-colors ${
          isConsoleOpen
            ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950/40 dark:text-blue-300'
            : 'border-slate-200 text-slate-500 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-900'
        }`}
        aria-label={isConsoleOpen ? 'Collapse console' : 'Open console'}
        data-testid="meeting-console-toggle"
      >
        <MessageSquare className="h-4 w-4" aria-hidden="true" />
      </button>
      <div className="hidden shrink-0 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400 md:block">
        Pack tools
      </div>
      <select
        value={selectedPackToolId}
        disabled={isDispatching || !hasActiveMeeting}
        onChange={(event) => onSelectedPackToolChange(event.target.value)}
        className="h-9 w-44 shrink-0 rounded-md border border-slate-200 bg-slate-50 px-2 text-xs font-medium text-slate-700 outline-none transition-colors focus:border-blue-400 focus:bg-white dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200 dark:focus:border-blue-500"
        aria-label="Meeting pack tool"
        data-testid="meeting-pack-tool-select"
        title={packToolsError || selectedPackTool?.description || 'Auto route through the workspace runtime'}
      >
        <option value="auto">{packToolsLoading ? 'Loading tools...' : 'Auto route'}</option>
        {packTools.map((tool) => (
          <option key={tool.id} value={tool.id}>
            {tool.capabilityCode ? `${tool.capabilityCode} / ${tool.label}` : tool.label}
          </option>
        ))}
      </select>
      <div className="relative min-w-0 flex-1">
        <input
          value={command}
          disabled={isDispatching || !hasActiveMeeting}
          onChange={(event) => onCommandChange(event.target.value)}
          className="h-9 w-full rounded-md border border-slate-200 bg-slate-50 px-3 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-blue-400 focus:bg-white dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-blue-500"
          placeholder={
            isDispatching
              ? 'Dispatching...'
              : !hasActiveMeeting
                ? 'Select a meeting session first...'
                : selectedPackTool
                ? `Ask ${selectedPackTool.label} to do the next step...`
                : 'Ask a pack tool or type @ to reference context...'
          }
          aria-label="Meeting instruction"
          aria-autocomplete="list"
          aria-expanded={showMentionPicker}
        />
        {showMentionPicker ? (
          <div
            className="absolute bottom-11 left-0 z-40 w-[min(34rem,calc(100vw-8rem))] overflow-hidden rounded-lg border border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-950"
            data-testid="meeting-mention-picker"
            role="listbox"
            aria-label="Meeting references"
          >
            <div className="border-b border-slate-200 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:border-slate-800 dark:text-slate-400">
              Insert reference
            </div>
            {mentionOptions.length > 0 ? (
              <div className="max-h-64 overflow-auto py-1">
                {mentionOptions.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onMouseDown={(event) => {
                      event.preventDefault();
                      applyMention(item);
                    }}
                    className="flex w-full items-start gap-2 px-3 py-2 text-left text-xs transition-colors hover:bg-slate-100 dark:hover:bg-slate-900"
                    role="option"
                    data-testid={`meeting-mention-option-${item.id}`}
                  >
                    <span className="mt-0.5 shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-slate-500 dark:bg-slate-900 dark:text-slate-400">
                      {item.kind}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-semibold text-slate-900 dark:text-slate-100">
                        {item.label}
                      </span>
                      <span className="block truncate text-slate-500 dark:text-slate-400">
                        {item.description}
                      </span>
                    </span>
                    <span className="shrink-0 font-mono text-[11px] text-blue-600 dark:text-blue-300">
                      {item.token}
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <div className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">
                {mentionItemsLoading
                  ? 'Loading references...'
                  : mentionItemsError
                    ? `Reference search partially unavailable: ${mentionItemsError}`
                    : 'No matching object, storyboard, scene, character, session, node, or pack.'}
              </div>
            )}
          </div>
        ) : null}
      </div>
      <button
        type="submit"
        className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-slate-900 text-white transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300 dark:bg-slate-100 dark:text-slate-950 dark:hover:bg-white dark:disabled:bg-slate-700 dark:disabled:text-slate-400"
        aria-label="Send meeting instruction"
        disabled={!hasActiveMeeting || !command.trim() || isDispatching}
      >
        <Send className="h-4 w-4" aria-hidden="true" />
      </button>
    </form>
  );
}

function MeetingInspectorRail({
  activeInspector,
  onToggleInspector,
}: {
  activeInspector: InspectorTab | null;
  onToggleInspector: (tab: InspectorTab) => void;
}) {
  return (
    <nav
      className="flex w-12 shrink-0 flex-col items-center gap-2 border-l border-slate-200 bg-white px-1.5 py-3 dark:border-slate-800 dark:bg-slate-950"
      data-testid="meeting-inspector-rail"
      aria-label="Meeting inspector"
    >
      {INSPECTOR_TABS.map((tab) => {
        const Icon = tab.icon;
        const isActive = tab.id === activeInspector;
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onToggleInspector(tab.id)}
            className={`inline-flex h-9 w-9 items-center justify-center rounded-md border transition-colors ${
              isActive
                ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950/40 dark:text-blue-300'
                : 'border-transparent text-slate-500 hover:border-slate-200 hover:bg-slate-100 dark:text-slate-400 dark:hover:border-slate-800 dark:hover:bg-slate-900'
            }`}
            aria-label={`${isActive ? 'Close' : 'Open'} ${tab.label} inspector`}
            title={tab.label}
            data-testid={`meeting-inspector-tab-${tab.id}`}
          >
            <Icon className="h-4 w-4" aria-hidden="true" />
          </button>
        );
      })}
    </nav>
  );
}

function MeetingInspectorPanel({
  activeInspector,
  selectedNode,
  runtimeSnapshot,
  workspaceId,
  apiUrl,
  meetingId,
  summary,
  attachResponse,
  objectGraphProjections,
  objectGraphLoading,
  objectGraphError,
  commandImpact,
  traceEvents,
  eventCounts,
  activeTraceFilter,
  onTraceFilterChange,
  onClose,
}: {
  activeInspector: InspectorTab;
  selectedNode: MeetingNode | null;
  runtimeSnapshot: RuntimeInspectorSnapshot;
  workspaceId: string;
  apiUrl: string;
  meetingId: string;
  summary: AddressableObjectSummary | null;
  attachResponse: ObjectMeetingAttachResponse | null;
  objectGraphProjections: ObjectGraphProjection[];
  objectGraphLoading: boolean;
  objectGraphError: string | null;
  commandImpact: MeetingCommandImpact | null;
  traceEvents: MeetingEventSummary[];
  eventCounts: Record<string, number>;
  activeTraceFilter: string | null;
  onTraceFilterChange: (filter: string | null) => void;
  onClose: () => void;
}) {
  const title = INSPECTOR_TABS.find((tab) => tab.id === activeInspector)?.label ?? 'Inspector';
  const traceFilterOptions = Object.entries(eventCounts)
    .filter(([type, count]) => count > 0 && !type.startsWith('collapsed_') && type !== 'executable_action_item')
    .sort(([left], [right]) => left.localeCompare(right));
  const filteredTraceEvents = traceEvents.filter((event) => {
    if (!activeTraceFilter) {
      return true;
    }
    const type = getEventType(event);
    if (activeTraceFilter === 'decision') {
      return type.startsWith('decision_');
    }
    return type === activeTraceFilter;
  });
  const selectedTraceEvent = selectedNode?.eventIds?.length
    ? traceEvents.find((event) => selectedNode.eventIds?.includes(event.id)) ?? filteredTraceEvents[0] ?? null
    : filteredTraceEvents[0] ?? null;

  return (
    <aside
      className="flex w-[340px] shrink-0 flex-col border-l border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950"
      data-testid="meeting-inspector-panel"
    >
      <div className="flex h-11 shrink-0 items-center justify-between border-b border-slate-200 px-3 dark:border-slate-800">
        <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
          {title}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100"
          aria-label="Close inspector"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3 text-sm text-slate-700 dark:text-slate-200">
        {activeInspector === 'object' ? (
          <div className="space-y-3">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                Selected
              </div>
              <div className="mt-1 font-semibold text-slate-950 dark:text-slate-100">
                {summary?.title || 'Selected object'}
              </div>
              <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">
                {summary?.summary_text || 'Object context is attached to this meeting.'}
              </p>
            </div>
            <div className="rounded-md border border-slate-200 p-2 text-xs dark:border-slate-800">
              <div className="font-mono text-slate-700 dark:text-slate-200">
                {summary?.ref.uri || 'mindscape://object'}
              </div>
            </div>
          </div>
        ) : null}

        {activeInspector === 'runtime' ? (
          <div className="space-y-3">
            <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
              <div className="flex items-center gap-2 font-semibold text-slate-950 dark:text-slate-100">
                <Cpu className="h-4 w-4" aria-hidden="true" />
                Runtime binding
              </div>
              <div className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
                Runtime state is inspector-scoped so it does not permanently consume bottom shell width.
              </div>
              <dl className="mt-3 grid gap-2 text-xs">
                <div className="rounded-md bg-slate-50 px-2 py-1.5 dark:bg-slate-900">
                  <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">Resolved</dt>
                  <dd className="mt-1 font-mono text-slate-800 dark:text-slate-100">
                    {runtimeSnapshot.resolvedRuntime || 'Mindscape default'}
                  </dd>
                </div>
                <div className="rounded-md bg-slate-50 px-2 py-1.5 dark:bg-slate-900">
                  <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">Dispatch chain</dt>
                  <dd className="mt-1 truncate font-mono text-slate-800 dark:text-slate-100">
                    {runtimeSnapshot.dispatchChain.length > 0
                      ? runtimeSnapshot.dispatchChain.join(' -> ')
                      : 'default'}
                  </dd>
                </div>
              </dl>
              {runtimeSnapshot.loading ? (
                <div className="mt-3 rounded-md bg-slate-100 px-2 py-1.5 text-xs text-slate-500 dark:bg-slate-900 dark:text-slate-400">
                  Loading runtime state...
                </div>
              ) : null}
              {runtimeSnapshot.error ? (
                <div className="mt-3 rounded-md bg-amber-50 px-2 py-1.5 text-xs text-amber-700 dark:bg-amber-950/20 dark:text-amber-300">
                  {runtimeSnapshot.error}
                </div>
              ) : null}
              <div className="mt-3 space-y-1.5">
                {runtimeSnapshot.agents.slice(0, 5).map((agent) => {
                  const isBound =
                    runtimeSnapshot.boundRuntimeIds.includes(agent.id) ||
                    runtimeSnapshot.resolvedRuntime === agent.id;
                  const isAvailable = agent.status === 'available';
                  const badgeLabel = isAvailable && isBound
                    ? 'bound live'
                    : isAvailable
                      ? 'available'
                      : isBound
                        ? 'route-bound'
                        : 'offline';
                  return (
                    <div
                      key={agent.id}
                      className="rounded-md border border-slate-200 px-2 py-1.5 text-xs dark:border-slate-800"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate font-semibold text-slate-800 dark:text-slate-100">
                          {agent.name || agent.id}
                        </span>
                        <span
                          className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                            isAvailable
                              ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300'
                              : isBound
                                ? 'bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-300'
                                : 'bg-slate-100 text-slate-500 dark:bg-slate-900 dark:text-slate-400'
                          }`}
                        >
                          {badgeLabel}
                        </span>
                      </div>
                      {isBound && !isAvailable ? (
                        <div className="mt-1 text-slate-500 dark:text-slate-400">
                          Route is configured, but no live workspace bridge is reporting availability.
                        </div>
                      ) : null}
                      {agent.reason || agent.transport ? (
                        <div className="mt-1 truncate text-slate-500 dark:text-slate-400">
                          {agent.transport || agent.reason}
                        </div>
                      ) : null}
                    </div>
                  );
                })}
                {runtimeSnapshot.agents.length === 0 && !runtimeSnapshot.loading ? (
                  <div className="rounded-md border border-slate-200 px-2 py-1.5 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
                    No runtime agents reported.
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}

        {activeInspector === 'session' ? (
          <dl className="grid gap-2 text-xs">
            <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
              <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">Meeting</dt>
              <dd className="mt-1 font-mono">{meetingId}</dd>
            </div>
            <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
              <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">Workspace</dt>
              <dd className="mt-1 font-mono">{workspaceId}</dd>
            </div>
            <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
              <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">API</dt>
              <dd className="mt-1 truncate font-mono">{apiUrl}</dd>
            </div>
          </dl>
        ) : null}

        {activeInspector === 'trace' ? (
          <div className="space-y-3" data-testid="meeting-trace-panel">
            {commandImpact ? (
              <div className="rounded-md border border-blue-200 bg-blue-50/70 p-2 text-xs dark:border-blue-900 dark:bg-blue-950/20" data-testid="meeting-command-impact-panel">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-semibold text-blue-950 dark:text-blue-100">Command impact</div>
                  <span className="rounded bg-white/80 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-blue-700 dark:bg-blue-950/70 dark:text-blue-200">
                    {commandImpact.phase}
                  </span>
                </div>
                <div className="mt-2 rounded bg-white/80 p-2 font-medium leading-5 text-slate-900 dark:bg-slate-950/70 dark:text-slate-100">
                  {commandImpact.commandText}
                </div>
                <dl className="mt-2 grid grid-cols-2 gap-1.5 text-[11px] text-slate-600 dark:text-slate-300">
                  <div className="rounded bg-white/70 px-2 py-1 dark:bg-slate-950/50">
                    <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">Status</dt>
                    <dd className="mt-0.5">{commandImpact.status}</dd>
                  </div>
                  <div className="rounded bg-white/70 px-2 py-1 dark:bg-slate-950/50">
                    <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">Edges</dt>
                    <dd className="mt-0.5">{commandImpact.edgeIds.size}</dd>
                  </div>
                  <div className="rounded bg-white/70 px-2 py-1 dark:bg-slate-950/50">
                    <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">Decisions</dt>
                    <dd className="mt-0.5">{commandImpact.decisions.length}</dd>
                  </div>
                  <div className="rounded bg-white/70 px-2 py-1 dark:bg-slate-950/50">
                    <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">Actions</dt>
                    <dd className="mt-0.5">{commandImpact.actionItems.length}</dd>
                  </div>
                  <div className="rounded bg-white/70 px-2 py-1 dark:bg-slate-950/50">
                    <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">Outputs</dt>
                    <dd className="mt-0.5">{commandImpact.outputs.length}</dd>
                  </div>
                  <div className="rounded bg-white/70 px-2 py-1 dark:bg-slate-950/50">
                    <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">Artifacts</dt>
                    <dd className="mt-0.5">{commandImpact.artifacts.length}</dd>
                  </div>
                </dl>
                <div className="mt-2 max-h-28 space-y-1 overflow-auto">
                  {commandImpact.relatedNodes.slice(0, 8).map((node) => (
                    <div key={node.id} className="rounded bg-white/70 px-2 py-1 text-[11px] dark:bg-slate-950/50">
                      <span className="font-semibold">{node.eyebrow}</span>
                      <span className="mx-1 text-slate-400">/</span>
                      <span>{node.title}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="rounded-md border border-slate-200 p-2 text-xs dark:border-slate-800">
              <div className="flex items-center justify-between gap-2">
                <div className="font-semibold text-slate-900 dark:text-slate-100">Raw replay events</div>
                <div className="rounded bg-slate-100 px-1.5 py-0.5 font-semibold tabular-nums text-slate-500 dark:bg-slate-900 dark:text-slate-400">
                  {filteredTraceEvents.length}/{traceEvents.length}
                </div>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <button
                  type="button"
                  onClick={() => onTraceFilterChange(null)}
                  className={`rounded border px-2 py-1 text-[11px] font-semibold ${
                    activeTraceFilter === null
                      ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950/40 dark:text-blue-300'
                      : 'border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-slate-800 dark:text-slate-400 dark:hover:bg-slate-900'
                  }`}
                  data-testid="meeting-trace-filter-all"
                  aria-pressed={activeTraceFilter === null}
                >
                  All
                </button>
                {traceFilterOptions.map(([type, count]) => (
                  <button
                    key={type}
                    type="button"
                    onClick={() => onTraceFilterChange(type)}
                    className={`rounded border px-2 py-1 text-[11px] font-semibold ${
                      activeTraceFilter === type
                        ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950/40 dark:text-blue-300'
                        : 'border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-slate-800 dark:text-slate-400 dark:hover:bg-slate-900'
                    }`}
                    data-testid={`meeting-trace-filter-${type}`}
                    aria-pressed={activeTraceFilter === type}
                  >
                    {formatKind(type)} {count}
                  </button>
                ))}
              </div>
            </div>
            <div
              className="max-h-44 space-y-1.5 overflow-auto rounded-md border border-slate-200 p-2 dark:border-slate-800"
              data-testid="meeting-trace-event-list"
            >
              {filteredTraceEvents.slice(0, 80).map((event) => {
                const type = getEventType(event);
                return (
                  <div
                    key={event.id}
                    className={`rounded px-2 py-1.5 text-xs ${
                      selectedTraceEvent?.id === event.id
                        ? 'bg-blue-50 text-blue-800 dark:bg-blue-950/30 dark:text-blue-200'
                        : 'bg-slate-50 text-slate-600 dark:bg-slate-900 dark:text-slate-300'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-semibold">{formatKind(type)}</span>
                      <span className="shrink-0 font-mono text-[10px] opacity-70">
                        {formatEventTime(event.timestamp)}
                      </span>
                    </div>
                    <div className="mt-0.5 truncate text-[11px] opacity-75">{getEventTitle(event)}</div>
                  </div>
                );
              })}
              {filteredTraceEvents.length === 0 ? (
                <div className="rounded-md border border-dashed border-slate-200 px-2 py-3 text-xs text-slate-400 dark:border-slate-800 dark:text-slate-500">
                  No events for this filter.
                </div>
              ) : null}
            </div>
            <pre
              className="max-h-44 overflow-auto rounded-md bg-slate-100 p-2 text-[11px] leading-5 text-slate-700 dark:bg-slate-900 dark:text-slate-300"
              data-testid="meeting-trace-event-json"
            >
              {selectedTraceEvent ? JSON.stringify(selectedTraceEvent, null, 2) : 'No event selected.'}
            </pre>
          </div>
        ) : null}

        {activeInspector === 'graph' ? (
          <div className="space-y-3" data-testid="meeting-object-graph-panel">
            <div className="rounded-md border border-slate-200 p-2 text-xs dark:border-slate-800">
              <div className="flex items-center justify-between gap-2">
                <div className="font-semibold text-slate-900 dark:text-slate-100">Bounded object graph</div>
                <div className="rounded bg-slate-100 px-1.5 py-0.5 font-semibold tabular-nums text-slate-500 dark:bg-slate-900 dark:text-slate-400">
                  {objectGraphProjections.length}
                </div>
              </div>
              {objectGraphLoading ? (
                <div className="mt-2 text-slate-500 dark:text-slate-400">Loading bounded relation projections...</div>
              ) : null}
              {objectGraphError ? (
                <div className="mt-2 rounded bg-amber-50 px-2 py-1.5 text-amber-700 dark:bg-amber-950/20 dark:text-amber-300">
                  {objectGraphError}
                </div>
              ) : null}
            </div>
            <div className="max-h-56 space-y-2 overflow-auto">
              {objectGraphProjections.map((projection) => (
                <div
                  key={addressableRefKey(projection.ref)}
                  className="rounded-md border border-slate-200 p-2 text-xs dark:border-slate-800"
                >
                  <div className="font-semibold text-slate-900 dark:text-slate-100">
                    {projection.summary?.title || graphRefLabel(projection.ref)}
                  </div>
                  <div className="mt-1 truncate font-mono text-[11px] text-slate-500 dark:text-slate-400">
                    {projection.ref.uri || graphRefLabel(projection.ref)}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {(projection.relations || []).slice(0, 6).map((relation, index) => (
                      <span
                        key={`${relation.relation_kind}-${index}`}
                        className="rounded-full bg-slate-100 px-2 py-1 text-[11px] text-slate-600 dark:bg-slate-900 dark:text-slate-300"
                      >
                        {relation.direction} {relation.relation_kind}
                      </span>
                    ))}
                    {(projection.relations || []).length === 0 ? (
                      <span className="text-slate-400 dark:text-slate-500">No bounded relations</span>
                    ) : null}
                  </div>
                </div>
              ))}
              {objectGraphProjections.length === 0 && !objectGraphLoading ? (
                <div className="rounded-md border border-dashed border-slate-200 px-2 py-3 text-xs text-slate-400 dark:border-slate-800 dark:text-slate-500">
                  No graph projection available for the selected objects.
                </div>
              ) : null}
            </div>
            {selectedNode?.lane === 'graph' && selectedNode.output ? (
              <pre className="max-h-44 overflow-auto rounded-md bg-slate-100 p-2 text-[11px] leading-5 text-slate-700 dark:bg-slate-900 dark:text-slate-300">
                {selectedNode.output}
              </pre>
            ) : null}
          </div>
        ) : null}

        {activeInspector === 'prompts' ? (
          <div className="space-y-2 text-xs">
            <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
              Next prompt is created through the command bar and appears as a task node.
            </div>
          </div>
        ) : null}

        {activeInspector === 'patch' ? (
          <div className="space-y-2 text-xs">
            {(attachResponse?.review_routes ?? []).length > 0 ? (
              attachResponse?.review_routes.map((route) => (
                <a
                  key={route}
                  href={route}
                  className="block rounded-md border border-slate-200 p-2 text-slate-700 hover:bg-slate-50 dark:border-slate-800 dark:text-slate-200 dark:hover:bg-slate-900"
                >
                  {route}
                </a>
              ))
            ) : (
              <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
                No review routes staged.
              </div>
            )}
          </div>
        ) : null}

        <div className="mt-3 rounded-md border border-slate-200 p-2 text-xs dark:border-slate-800">
          <div className="font-semibold text-slate-900 dark:text-slate-100">Selected node</div>
          <div className="mt-1 text-slate-500 dark:text-slate-400">
            {selectedNode ? `${selectedNode.eyebrow}: ${selectedNode.title}` : 'none'}
          </div>
        </div>
      </div>
    </aside>
  );
}

function MeetingConsoleDrawer({
  selectedNode,
  onClose,
}: {
  selectedNode: MeetingNode | null;
  onClose: () => void;
}) {
  return (
    <section
      className="h-[38%] max-h-40 shrink-0 border-t border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950"
      data-testid="meeting-console-drawer"
      aria-label="Meeting console"
    >
      <div className="flex h-9 items-center justify-between border-b border-slate-200 px-3 dark:border-slate-800">
        <div className="text-xs font-semibold text-slate-800 dark:text-slate-100">
          Console: {selectedNode?.title || 'Selected node'}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100"
          aria-label="Collapse console"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <div className="grid h-[calc(100%-2.25rem)] grid-cols-[minmax(0,1fr)_220px] gap-3 overflow-auto px-3 py-2 text-xs">
        <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
          <div className="font-semibold text-slate-900 dark:text-slate-100">Node detail</div>
          <p className="mt-1 leading-5 text-slate-500 dark:text-slate-400">
            {selectedNode?.detail || 'Select a graph node to inspect details.'}
          </p>
          {selectedNode?.output ? (
            <p className="mt-2 rounded bg-slate-100 px-2 py-1 font-mono text-[11px] text-slate-600 dark:bg-slate-900 dark:text-slate-300">
              {selectedNode.output}
            </p>
          ) : null}
        </div>
        <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
          <div className="font-semibold text-slate-900 dark:text-slate-100">Runtime output</div>
          <p className="mt-1 leading-5 text-slate-500 dark:text-slate-400">
            Waiting for the first execution event.
          </p>
        </div>
      </div>
    </section>
  );
}

export function AOLMeetingBottomShell({
  workspaceId,
  apiUrl,
  meetingId,
  summary,
  selection,
  attachResponse,
  surfaceRoute,
  onSwitchObject,
}: AOLMeetingBottomShellProps) {
  const t = useT();
  const [selectedNodeId, setSelectedNodeId] = useState('ready');
  const [activeInspector, setActiveInspector] = useState<InspectorTab | null>(null);
  const [activeInfoPanel, setActiveInfoPanel] = useState<MeetingInfoPanel | null>(null);
  const [graphViewMode, setGraphViewMode] = useState<GraphViewMode>('flow');
  const [activeTraceFilter, setActiveTraceFilter] = useState<string | null>(null);
  const [isConsoleOpen, setIsConsoleOpen] = useState(false);
  const [command, setCommand] = useState('');
  const [localTasks, setLocalTasks] = useState<MeetingNode[]>([]);
  const [dispatchError, setDispatchError] = useState<string | null>(null);
  const [canvasZoom, setCanvasZoom] = useState(1);
  const [packTools, setPackTools] = useState<MeetingPackTool[]>([]);
  const [selectedPackToolId, setSelectedPackToolId] = useState('auto');
  const [packToolsLoading, setPackToolsLoading] = useState(false);
  const [packToolsError, setPackToolsError] = useState<string | null>(null);
  const [registryMentionItems, setRegistryMentionItems] = useState<MeetingMentionItem[]>([]);
  const [appliedMentionItems, setAppliedMentionItems] = useState<MeetingMentionItem[]>([]);
  const [registryMentionItemsLoading, setRegistryMentionItemsLoading] = useState(false);
  const [registryMentionItemsError, setRegistryMentionItemsError] = useState<string | null>(null);
  const [activeMeetingId, setActiveMeetingId] = useState(meetingId ?? '');
  const [meetingSessions, setMeetingSessions] = useState<MeetingSessionSummary[]>([]);
  const [meetingSessionsLoading, setMeetingSessionsLoading] = useState(false);
  const [meetingSessionsError, setMeetingSessionsError] = useState<string | null>(null);
  const [meetingEvents, setMeetingEvents] = useState<MeetingEventSummary[]>([]);
  const [meetingEventsLoading, setMeetingEventsLoading] = useState(false);
  const [meetingEventsError, setMeetingEventsError] = useState<string | null>(null);
  const [executionGraphNodes, setExecutionGraphNodes] = useState<MeetingNode[]>([]);
  const [executionGraphEdges, setExecutionGraphEdges] = useState<MeetingGraphEdge[]>([]);
  const [executionGraphLoading, setExecutionGraphLoading] = useState(false);
  const [executionGraphError, setExecutionGraphError] = useState<string | null>(null);
  const [objectGraphProjections, setObjectGraphProjections] = useState<ObjectGraphProjection[]>([]);
  const [objectGraphLoading, setObjectGraphLoading] = useState(false);
  const [objectGraphError, setObjectGraphError] = useState<string | null>(null);
  const [meetingArtifacts, setMeetingArtifacts] = useState<MeetingArtifactSummary[]>([]);
  const [meetingArtifactsLoading, setMeetingArtifactsLoading] = useState(false);
  const [meetingArtifactsError, setMeetingArtifactsError] = useState<string | null>(null);
  const { sendMessage, isLoading: isDispatching } = useSendMessage(workspaceId, apiUrl, undefined, activeMeetingId);
  const activeMentionQuery = getMentionQuery(command);
  const [runtimeSnapshot, setRuntimeSnapshot] = useState<RuntimeInspectorSnapshot>({
    resolvedRuntime: null,
    dispatchChain: [],
    boundRuntimeIds: [],
    agents: [],
    loading: false,
    error: null,
  });

  useEffect(() => {
    setActiveMeetingId(meetingId ?? '');
  }, [meetingId]);

  useEffect(() => {
    let cancelled = false;

    async function fetchMeetingSessions() {
      setMeetingSessionsLoading(true);
      setMeetingSessionsError(null);

      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/meeting-sessions?limit=100`,
        );
        if (!response.ok) {
          throw new Error(`Failed to fetch meeting sessions: ${response.status}`);
        }
        const data = await response.json() as { sessions?: unknown };
        if (cancelled) {
          return;
        }
        const rawSessions = Array.isArray(data.sessions) ? data.sessions : [];
        const sessions = rawSessions
          .filter(isRecord)
          .map((session: Record<string, unknown>) => session as unknown as MeetingSessionSummary);
        setMeetingSessions(sessions);
        setActiveMeetingId((current) => current || sessions[0]?.id || '');
      } catch (error) {
        if (!cancelled) {
          setMeetingSessions([]);
          setMeetingSessionsError(error instanceof Error ? error.message : 'Failed to load meeting sessions.');
        }
      } finally {
        if (!cancelled) {
          setMeetingSessionsLoading(false);
        }
      }
    }

    void fetchMeetingSessions();

    return () => {
      cancelled = true;
    };
  }, [apiUrl, meetingId, workspaceId]);

  useEffect(() => {
    setLocalTasks([]);
    setMeetingEvents([]);
    setMeetingEventsError(null);
    setExecutionGraphNodes([]);
    setExecutionGraphEdges([]);
    setExecutionGraphError(null);
    setMeetingArtifacts([]);
    setMeetingArtifactsError(null);
    setActiveTraceFilter(null);
    setAppliedMentionItems([]);
  }, [activeMeetingId]);

  useEffect(() => {
    let cancelled = false;

    async function fetchExecutionGraph() {
      if (!activeMeetingId) {
        setExecutionGraphNodes([]);
        setExecutionGraphEdges([]);
        return;
      }

      setExecutionGraphLoading(true);
      setExecutionGraphError(null);

      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/meetings/${encodeURIComponent(
            activeMeetingId,
          )}/execution-graph?limit=200`,
        );
        if (!response.ok) {
          throw new Error(`Failed to fetch meeting execution graph: ${response.status}`);
        }

        const data = await response.json() as MeetingExecutionGraphPayload;
        const rawNodes = Array.isArray(data.nodes) ? data.nodes : [];
        const nodes = rawNodes
          .map(coerceExecutionGraphNode)
          .filter((node): node is MeetingNode => Boolean(node));
        const rawEdges = Array.isArray(data.edges) ? data.edges : [];
        const edges = rawEdges
          .map(coerceExecutionGraphEdge)
          .filter((edge): edge is MeetingGraphEdge => Boolean(edge));

        if (!cancelled) {
          setExecutionGraphNodes(nodes);
          setExecutionGraphEdges(edges);
        }
      } catch (error) {
        if (!cancelled) {
          setExecutionGraphNodes([]);
          setExecutionGraphEdges([]);
          setExecutionGraphError(error instanceof Error ? error.message : 'Failed to load execution graph.');
        }
      } finally {
        if (!cancelled) {
          setExecutionGraphLoading(false);
        }
      }
    }

    void fetchExecutionGraph();

    function handleWorkspaceUpdate() {
      void fetchExecutionGraph();
    }

    window.addEventListener('workspace-chat-updated', handleWorkspaceUpdate);
    window.addEventListener('workspace-task-updated', handleWorkspaceUpdate);

    return () => {
      cancelled = true;
      window.removeEventListener('workspace-chat-updated', handleWorkspaceUpdate);
      window.removeEventListener('workspace-task-updated', handleWorkspaceUpdate);
    };
  }, [activeMeetingId, apiUrl, workspaceId]);

  useEffect(() => {
    let cancelled = false;

    async function readEventsFromResponse(response: Response): Promise<MeetingEventSummary[]> {
      if (!response.ok) {
        throw new Error(`Failed to fetch meeting events: ${response.status}`);
      }
      const data = await response.json() as { events?: unknown };
      const rawEvents = Array.isArray(data.events) ? data.events : [];
      return rawEvents
        .filter(isRecord)
        .map((event: Record<string, unknown>) => event as unknown as MeetingEventSummary)
        .sort((a, b) => {
          const left = a.timestamp ? new Date(a.timestamp).getTime() : 0;
          const right = b.timestamp ? new Date(b.timestamp).getTime() : 0;
          return left - right || a.id.localeCompare(b.id);
        });
    }

    async function fetchMeetingEvents() {
      if (!activeMeetingId) {
        setMeetingEvents([]);
        return;
      }

      setMeetingEventsLoading(true);
      setMeetingEventsError(null);

      try {
        const sessionEventsResponse = await fetch(
          `${apiUrl}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/meeting-sessions/${encodeURIComponent(activeMeetingId)}/events?limit=120`,
        );
        let events = await readEventsFromResponse(sessionEventsResponse);

        if (events.length === 0) {
          const threadEventsResponse = await fetch(
            `${apiUrl}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/events?thread_id=${encodeURIComponent(activeMeetingId)}&limit=120`,
          );
          events = await readEventsFromResponse(threadEventsResponse);
        }

        if (!cancelled) {
          setMeetingEvents(events);
        }
      } catch (error) {
        if (!cancelled) {
          setMeetingEvents([]);
          setMeetingEventsError(error instanceof Error ? error.message : 'Failed to load meeting events.');
        }
      } finally {
        if (!cancelled) {
          setMeetingEventsLoading(false);
        }
      }
    }

    void fetchMeetingEvents();

    function handleWorkspaceUpdate() {
      void fetchMeetingEvents();
    }

    window.addEventListener('workspace-chat-updated', handleWorkspaceUpdate);
    window.addEventListener('workspace-task-updated', handleWorkspaceUpdate);

    return () => {
      cancelled = true;
      window.removeEventListener('workspace-chat-updated', handleWorkspaceUpdate);
      window.removeEventListener('workspace-task-updated', handleWorkspaceUpdate);
    };
  }, [activeMeetingId, apiUrl, workspaceId]);

  useEffect(() => {
    let cancelled = false;

    async function fetchMeetingArtifacts() {
      if (!activeMeetingId) {
        setMeetingArtifacts([]);
        return;
      }

      setMeetingArtifactsLoading(true);
      setMeetingArtifactsError(null);

      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/artifacts?thread_id=${encodeURIComponent(activeMeetingId)}&limit=80`,
        );
        if (!response.ok) {
          throw new Error(`Failed to fetch meeting artifacts: ${response.status}`);
        }
        const data = await response.json() as { artifacts?: unknown };
        const rawArtifacts = Array.isArray(data.artifacts) ? data.artifacts : [];
        const artifacts = rawArtifacts
          .filter(isRecord)
          .map((artifact: Record<string, unknown>) => artifact as unknown as MeetingArtifactSummary)
          .sort((a, b) => {
            const left = a.created_at ? new Date(a.created_at).getTime() : 0;
            const right = b.created_at ? new Date(b.created_at).getTime() : 0;
            return left - right || a.id.localeCompare(b.id);
          });

        if (!cancelled) {
          setMeetingArtifacts(artifacts);
        }
      } catch (error) {
        if (!cancelled) {
          setMeetingArtifacts([]);
          setMeetingArtifactsError(error instanceof Error ? error.message : 'Failed to load meeting artifacts.');
        }
      } finally {
        if (!cancelled) {
          setMeetingArtifactsLoading(false);
        }
      }
    }

    void fetchMeetingArtifacts();

    function handleWorkspaceUpdate() {
      void fetchMeetingArtifacts();
    }

    window.addEventListener('workspace-chat-updated', handleWorkspaceUpdate);
    window.addEventListener('workspace-task-updated', handleWorkspaceUpdate);

    return () => {
      cancelled = true;
      window.removeEventListener('workspace-chat-updated', handleWorkspaceUpdate);
      window.removeEventListener('workspace-task-updated', handleWorkspaceUpdate);
    };
  }, [activeMeetingId, apiUrl, workspaceId]);

  const activeSession = useMemo(
    () => meetingSessions.find((session) => session.id === activeMeetingId) ?? null,
    [activeMeetingId, meetingSessions],
  );
  const sessionSummary = useMemo(() => buildSessionObjectSummary(activeSession), [activeSession]);
  const sessionSelection = useMemo(() => buildSessionSelection(activeSession), [activeSession]);
  const sessionAttachResponse = useMemo(
    () => buildSessionAttachResponse(activeSession, workspaceId),
    [activeSession, workspaceId],
  );
  const effectiveSummary = sessionSummary ?? summary;
  const effectiveSelection = sessionSelection ?? selection;
  const effectiveAttachResponse = sessionAttachResponse ?? attachResponse;

  const objectTitle = effectiveSummary?.title || effectiveSelection?.label || 'Selected object';
  const objectKind = formatKind(effectiveSummary?.ref.object_kind || effectiveSelection?.objectKind);
  const hasObjectContext = Boolean(effectiveSummary || effectiveSelection || effectiveAttachResponse);
  const objectGraphRefs = useMemo(
    () => collectGraphProjectionRefs(effectiveSummary, effectiveAttachResponse),
    [effectiveAttachResponse, effectiveSummary],
  );
  const objectGraphRefKey = useMemo(
    () => objectGraphRefs.map(addressableRefKey).join('\n'),
    [objectGraphRefs],
  );

  useEffect(() => {
    let cancelled = false;

    async function fetchObjectGraph() {
      if (!workspaceId || objectGraphRefs.length === 0) {
        setObjectGraphProjections([]);
        setObjectGraphError(null);
        setObjectGraphLoading(false);
        return;
      }

      setObjectGraphLoading(true);
      setObjectGraphError(null);

      try {
        const response = await projectAddressableObjectGraph({
          apiUrl,
          workspaceId,
          objects: objectGraphRefs,
          includeRelations: true,
          includeSummaries: true,
        });

        if (!cancelled) {
          setObjectGraphProjections(response.projections || []);
        }
      } catch (error) {
        if (!cancelled) {
          setObjectGraphProjections([]);
          setObjectGraphError(error instanceof Error ? error.message : 'Failed to load object graph.');
        }
      } finally {
        if (!cancelled) {
          setObjectGraphLoading(false);
        }
      }
    }

    void fetchObjectGraph();

    function handleWorkspaceUpdate() {
      void fetchObjectGraph();
    }

    window.addEventListener('workspace-task-updated', handleWorkspaceUpdate);

    return () => {
      cancelled = true;
      window.removeEventListener('workspace-task-updated', handleWorkspaceUpdate);
    };
  }, [apiUrl, objectGraphRefKey, objectGraphRefs, workspaceId]);

  useEffect(() => {
    if (!workspaceId) {
      return;
    }

    const controller = new AbortController();

    async function syncObjectIndex(reason: string) {
      try {
        await postApiJson(
          apiUrl,
          `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/objects/sync`,
          {
            limit: 200,
            force: false,
            reason,
          },
          controller.signal,
        );
      } catch {
        // Mention completion uses the registry read model; sync failures surface through completion state.
      }
    }

    void syncObjectIndex('meeting_bottom_shell_open');

    function handleWorkspaceUpdate() {
      void syncObjectIndex('workspace_update');
    }

    window.addEventListener('workspace-task-updated', handleWorkspaceUpdate);

    return () => {
      controller.abort();
      window.removeEventListener('workspace-task-updated', handleWorkspaceUpdate);
    };
  }, [apiUrl, workspaceId]);

  useEffect(() => {
    let cancelled = false;

    async function fetchPackTools() {
      setPackToolsLoading(true);
      setPackToolsError(null);

      try {
        const query = 'scope=all&target_language=zh-TW&profile_id=default-user';
        const sameOriginUrl = `/api/v1/playbooks/?${query}`;
        const primaryUrl = `${apiUrl}/api/v1/playbooks/?${query}`;
        const urls = primaryUrl === sameOriginUrl ? [sameOriginUrl] : [primaryUrl, sameOriginUrl];
        let data: unknown = null;
        let lastError: unknown = null;

        for (const url of urls) {
          try {
            const response = await fetch(url);
            if (!response.ok) {
              throw new Error(`Failed to fetch playbooks: ${response.status}`);
            }
            data = await response.json();
            lastError = null;
            break;
          } catch (error) {
            lastError = error;
          }
        }

        if (lastError) {
          throw lastError;
        }

        if (cancelled) {
          return;
        }

        const playbooks = Array.isArray(data) ? data : [];
        const mappedTools = playbooks
          .map((playbook: Record<string, unknown>): MeetingPackTool | null => {
            const id = typeof playbook.playbook_code === 'string' ? playbook.playbook_code : '';
            if (!id) {
              return null;
            }

            const requiredTools = Array.isArray(playbook.required_tools)
              ? playbook.required_tools.filter((tool): tool is string => typeof tool === 'string')
              : [];
            const capabilityCode =
              typeof playbook.capability_code === 'string' && playbook.capability_code.trim()
                ? playbook.capability_code
                : null;

            return {
              id,
              label: typeof playbook.name === 'string' && playbook.name.trim() ? playbook.name : id,
              description:
                typeof playbook.description === 'string' && playbook.description.trim()
                  ? playbook.description
                  : 'Workspace playbook tool',
              capabilityCode,
              requiredTools,
            };
          })
          .filter((tool): tool is MeetingPackTool => Boolean(tool))
          .filter((tool) => Boolean(tool.capabilityCode) || tool.requiredTools.length > 0)
          .slice(0, 40);

        setPackTools(mappedTools);
      } catch (error) {
        if (!cancelled) {
          setPackTools([]);
          setPackToolsError(error instanceof Error ? error.message : 'Failed to load pack tools.');
        }
      } finally {
        if (!cancelled) {
          setPackToolsLoading(false);
        }
      }
    }

    void fetchPackTools();

    return () => {
      cancelled = true;
    };
  }, [apiUrl]);

  useEffect(() => {
    let cancelled = false;

    async function fetchRegistryMentionItems() {
      if (!workspaceId || !activeMeetingId || activeMentionQuery === null) {
        setRegistryMentionItems([]);
        setRegistryMentionItemsError(null);
        setRegistryMentionItemsLoading(false);
        return;
      }

      setRegistryMentionItemsLoading(true);
      setRegistryMentionItemsError(null);

      const params = new URLSearchParams({
        query: activeMentionQuery,
        limit: '16',
      });

      try {
        const payload = await fetchApiJson(
          apiUrl,
          `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/objects/complete?${params.toString()}`,
        );
        if (!cancelled) {
          const results = isRecord(payload) ? payload.results : [];
          setRegistryMentionItems(buildRegistryMentionItems(results));
          setRegistryMentionItemsLoading(false);
        }
      } catch (error) {
        if (!cancelled) {
          setRegistryMentionItems([]);
          setRegistryMentionItemsError(error instanceof Error ? error.message : 'object registry');
          setRegistryMentionItemsLoading(false);
        }
      }
    }

    void fetchRegistryMentionItems();

    return () => {
      cancelled = true;
    };
  }, [activeMeetingId, activeMentionQuery, apiUrl, workspaceId]);

  useEffect(() => {
    if (activeInspector !== 'runtime') {
      return;
    }

    let cancelled = false;

    async function fetchRuntimeState() {
      setRuntimeSnapshot((current) => ({
        ...current,
        loading: true,
        error: null,
      }));

      try {
        const [agentsResponse, specsResponse] = await Promise.all([
          fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/agents`),
          fetch(
            `${apiUrl}/api/v1/settings/model-route-registry/workspace-executor?workspace_id=${encodeURIComponent(workspaceId)}`
          ),
        ]);

        if (!agentsResponse.ok) {
          throw new Error(`Failed to fetch agents: ${agentsResponse.status}`);
        }
        if (!specsResponse.ok) {
          throw new Error(`Failed to fetch executor route policy: ${specsResponse.status}`);
        }

        const [agentsData, specsData] = await Promise.all([agentsResponse.json(), specsResponse.json()]);
        if (!cancelled) {
          const boundRuntimeIds = new Set<string>();
          const primaryRuntime = specsData.primary_executor_runtime || specsData.resolved_executor_runtime;
          if (primaryRuntime) {
            boundRuntimeIds.add(primaryRuntime);
          }
          Object.entries(specsData.surfaces || {}).forEach(([surface, state]) => {
            const surfaceState = state as { enabled?: boolean; preferred_runtime_id?: string | null };
            if (surfaceState.enabled) {
              boundRuntimeIds.add(surface);
            }
            if (surfaceState.preferred_runtime_id) {
              boundRuntimeIds.add(surfaceState.preferred_runtime_id);
            }
          });
          setRuntimeSnapshot({
            resolvedRuntime: primaryRuntime || null,
            dispatchChain: Array.isArray(specsData.dispatch_chain) ? specsData.dispatch_chain : [],
            boundRuntimeIds: Array.from(boundRuntimeIds),
            agents: Array.isArray(agentsData.agents) ? agentsData.agents : [],
            loading: false,
            error: null,
          });
        }
      } catch (error) {
        if (!cancelled) {
          setRuntimeSnapshot((current) => ({
            ...current,
            loading: false,
            error: error instanceof Error ? error.message : 'Failed to fetch runtime state.',
          }));
        }
      }
    }

    void fetchRuntimeState();

    return () => {
      cancelled = true;
    };
  }, [activeInspector, apiUrl, workspaceId]);

  const objectGraphNodes = useMemo(
    () => buildObjectGraphNodes(objectGraphProjections, objectGraphLoading, objectGraphError),
    [objectGraphError, objectGraphLoading, objectGraphProjections],
  );

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
  const selectedCommandImpact = useMemo(
    () => buildCommandImpact(selectedNode, nodes, graphProjection.edges, graphProjection.traceEvents),
    [graphProjection.edges, graphProjection.traceEvents, nodes, selectedNode],
  );
  const mentionItems = useMemo<MeetingMentionItem[]>(() => {
    const items: MeetingMentionItem[] = [];

    if (activeMeetingId) {
      const token = `@session:${shortId(activeMeetingId)}`;
      items.push({
        id: 'session-active',
        kind: 'session',
        label: `Session ${shortId(activeMeetingId)}`,
        token,
        description: 'Current meeting thread',
        searchText: `${activeMeetingId} meeting session active`,
        ref: createMentionReference({
          id: activeMeetingId,
          kind: 'session',
          token,
          label: `Session ${shortId(activeMeetingId)}`,
          description: 'Current meeting thread',
          sessionId: activeMeetingId,
          metadata: {
            active: true,
          },
        }),
      });
    }

    if (effectiveSummary?.ref.uri) {
      const token = `@object:${effectiveSummary.ref.object_id}`;
      items.push({
        id: 'object-current',
        kind: 'object',
        label: objectTitle,
        token,
        description: effectiveSummary.ref.uri,
        searchText: `${objectTitle} ${effectiveSummary.ref.uri} ${effectiveSummary.ref.object_kind} ${
          effectiveSummary.ref.owner_pack
        }`,
        ref: createMentionReference({
          id: effectiveSummary.ref.object_id,
          kind: 'object',
          token,
          label: objectTitle,
          description: effectiveSummary.ref.uri,
          uri: effectiveSummary.ref.uri,
          ownerPack: effectiveSummary.ref.owner_pack,
          objectKind: effectiveSummary.ref.object_kind,
          capabilityCode: effectiveSummary.ref.owner_pack,
          metadata: {
            source_surface: effectiveSummary.ref.source_surface,
          },
        }),
      });
    }

    appliedMentionItems.forEach((item) => {
      items.push(item);
    });

    registryMentionItems.forEach((item) => {
      items.push(item);
    });

    packTools.forEach((tool) => {
      const token = `@pack:${tool.id}`;
      items.push({
        id: `pack-${tool.id}`,
        kind: 'pack',
        label: tool.label,
        token,
        description: tool.capabilityCode ? `${tool.capabilityCode} pack tool` : tool.description,
        packToolId: tool.id,
        searchText: `${tool.label} ${tool.id} ${tool.description} ${tool.capabilityCode || ''} pack playbook tool`,
        ref: createMentionReference({
          id: tool.id,
          kind: 'pack',
          token,
          label: tool.label,
          description: tool.capabilityCode ? `${tool.capabilityCode} pack tool` : tool.description,
          ownerPack: tool.capabilityCode || undefined,
          objectKind: 'playbook',
          capabilityCode: tool.capabilityCode || undefined,
          metadata: {
            required_tools: tool.requiredTools,
          },
        }),
      });
    });

    nodes.forEach((node) => {
      const token = `@node:${node.id}`;
      items.push({
        id: `node-${node.id}`,
        kind: 'node',
        label: node.title,
        token,
        description: `${node.eyebrow} node`,
        searchText: `${node.title} ${node.detail} ${node.eyebrow} ${node.kind} ${node.lane}`,
        ref: createMentionReference({
          id: node.id,
          kind: 'node',
          token,
          label: node.title,
          description: `${node.eyebrow} node`,
          metadata: {
            node_kind: node.kind,
            lane: node.lane,
            status: node.status,
            event_ids: node.eventIds || [],
          },
        }),
      });
    });

    return items.filter((item, index, array) => {
      return array.findIndex((candidate) => candidate.token === item.token) === index;
    });
  }, [
    activeMeetingId,
    appliedMentionItems,
    effectiveSummary?.ref.object_id,
    effectiveSummary?.ref.object_kind,
    effectiveSummary?.ref.owner_pack,
    effectiveSummary?.ref.source_surface,
    effectiveSummary?.ref.uri,
    nodes,
    objectTitle,
    packTools,
    registryMentionItems,
  ]);

  function handleToggleInfoPanel(panel: MeetingInfoPanel) {
    setActiveInfoPanel((current) => (current === panel ? null : panel));
  }

  function handleCanvasZoom(delta: number) {
    setCanvasZoom((current) => clampCanvasZoom(current + delta));
  }

  function handleCanvasWheelZoom(deltaY: number) {
    const delta = deltaY < 0 ? CANVAS_ZOOM_STEP : -CANVAS_ZOOM_STEP;
    handleCanvasZoom(delta);
  }

  function handleApplyMention(item: MeetingMentionItem) {
    if (!item.ref && !item.packToolId) {
      return;
    }

    setAppliedMentionItems((current) => {
      const next = current.filter((candidate) => candidate.token !== item.token);
      next.push(item);
      return next.slice(-24);
    });
  }

  function handleToggleInspector(tab: InspectorTab) {
    setActiveInspector((current) => (current === tab ? null : tab));
  }

  function handleGraphViewModeChange(mode: GraphViewMode) {
    setGraphViewMode(mode);
    if (mode === 'trace') {
      setActiveInspector('trace');
    }
  }

  function handleSelectNode(nodeId: string) {
    const node = nodes.find((candidate) => candidate.id === nodeId) ?? null;
    setSelectedNodeId(nodeId);
    if (node?.traceFilter) {
      setActiveTraceFilter(node.traceFilter);
    }
    if (node?.kind === 'command') {
      setActiveInspector('trace');
      return;
    }
    if (node?.defaultInspector) {
      setActiveInspector(node.defaultInspector);
    }
  }

  async function requestObjectActionPlan(
    trimmedCommand: string,
    entries: MeetingObjectActionEntry[],
  ): Promise<Record<string, unknown> | null> {
    if (entries.length < 2) {
      return null;
    }

    try {
      const response = await fetch(
        `${apiUrl.replace(/\/$/, '')}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/object-actions/plan`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({
            instruction: trimmedCommand,
            meeting_id: activeMeetingId,
            entries,
            request_context: {
              source_surface: effectiveSummary?.ref.source_surface || 'meeting_graph',
              selected_object_uri: effectiveSummary?.ref.uri || null,
            },
          }),
        },
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        return {
          status: 'rejected',
          errors: [
            {
              code: 'object_action_plan_failed',
              message: isRecord(payload?.detail)
                ? readString(payload.detail.message) || `HTTP ${response.status}`
                : `HTTP ${response.status}`,
            },
          ],
        };
      }
      return isRecord(payload) ? payload : null;
    } catch (error) {
      return {
        status: 'rejected',
        errors: [
          {
            code: 'object_action_plan_failed',
            message: error instanceof Error ? error.message : 'Failed to plan object action.',
          },
        ],
      };
    }
  }

  function isPlannedObjectActionPlan(value: unknown): value is Record<string, unknown> {
    return isRecord(value) && readString(value.status) === 'planned' && isRecord(value.request_plan);
  }

  async function invokeObjectAction(
    trimmedCommand: string,
    objectActionPlan: Record<string, unknown>,
    entries: MeetingObjectActionEntry[],
  ): Promise<Record<string, unknown>> {
    const payload = await postApiJson(
      apiUrl,
      `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/object-actions/invoke`,
      {
        instruction: trimmedCommand,
        meeting_id: activeMeetingId,
        thread_id: activeMeetingId,
        object_action_plan: objectActionPlan,
        entries,
        request_context: {
          source_surface: effectiveSummary?.ref.source_surface || 'meeting_graph',
          selected_object_uri: effectiveSummary?.ref.uri || null,
        },
      },
    );
    if (!isRecord(payload)) {
      throw new Error('Object action invocation returned an invalid response.');
    }
    return payload;
  }

  async function handleSubmitCommand() {
    const trimmedCommand = command.trim();
    if (!trimmedCommand || !activeMeetingId) {
      return;
    }

    const meetingMentionRefs = extractMentionReferences(trimmedCommand, mentionItems);
    const explicitPackRef = meetingMentionRefs.find((ref) => ref.kind === 'pack');
    const selectedPackTool =
      (explicitPackRef
        ? packTools.find((tool) => {
            const qualifiedId = tool.capabilityCode ? `${tool.capabilityCode}.${tool.id}` : tool.id;
            return tool.id === explicitPackRef.id || qualifiedId === explicitPackRef.id;
          }) ?? null
        : null) ?? packTools.find((tool) => tool.id === selectedPackToolId) ?? null;
    const objectActionEntries = buildObjectActionPlanEntries(effectiveSummary?.ref, meetingMentionRefs);
    const nextNodeId = `task-${localTasks.length + 1}`;
    const nextNode: MeetingNode = {
      id: nextNodeId,
      eyebrow: selectedPackTool?.capabilityCode || 'Pack tool',
      title: trimmedCommand,
      detail: selectedPackTool
        ? `Dispatching through ${selectedPackTool.label}.`
        : 'Dispatching to the meeting thread.',
      status: 'running',
      kind: 'run',
      lane: 'runs',
    };

    setLocalTasks((current) => [...current, nextNode]);
    setSelectedNodeId(nextNodeId);
    setCommand('');
    setIsConsoleOpen(true);
    setDispatchError(null);

    const objectActionPlan = await requestObjectActionPlan(trimmedCommand, objectActionEntries);

    const meetingActionParams = {
      meeting_id: activeMeetingId,
      meeting_session_id: activeMeetingId,
      thread_id: activeMeetingId,
      meeting_command: trimmedCommand,
      selected_object_uri: effectiveSummary?.ref.uri,
      selected_object_title: objectTitle,
      selected_object_kind: effectiveSummary?.ref.object_kind || effectiveSelection?.objectKind,
      source_surface: effectiveSummary?.ref.source_surface || 'meeting_graph',
      meeting_mentions: meetingMentionRefs,
      target_storyboards: meetingMentionRefs.filter(isStoryboardReference),
      target_storyboard_scenes: meetingMentionRefs.filter(isStoryboardSceneReference),
      character_refs: meetingMentionRefs.filter(isCharacterReference),
      object_action_entries: objectActionEntries,
      object_action_plan: objectActionPlan,
    };

    try {
      if (isPlannedObjectActionPlan(objectActionPlan)) {
        const invokeResult = await invokeObjectAction(trimmedCommand, objectActionPlan, objectActionEntries);
        setLocalTasks((current) =>
          current.map((node) =>
            node.id === nextNodeId
              ? {
                  ...node,
                  detail:
                    readString(invokeResult.status) === 'succeeded'
                      ? t('meetingObjectActionCompleted')
                      : t('meetingObjectActionNoClosure'),
                  status: readString(invokeResult.status) === 'failed' ? 'error' : 'ready',
                  output: readString(invokeResult.execution_id)
                    ? t('meetingExecutionId', { executionId: readString(invokeResult.execution_id) })
                    : t('meetingObjectActionInvoked'),
                }
              : node,
          ),
        );
        window.dispatchEvent(new CustomEvent('workspace-task-updated'));
        return;
      }

      const result = selectedPackTool
        ? await sendMessage({
            message: `Meeting graph command for ${selectedPackTool.label}: ${trimmedCommand}`,
            action: 'execute_playbook',
            action_params: {
              ...meetingActionParams,
              playbook_code: selectedPackTool.id,
              instruction: trimmedCommand,
              message: trimmedCommand,
            },
            mode: 'auto',
            stream: true,
            thread_id: activeMeetingId,
          })
        : await sendMessage({
            message: `Meeting graph command for attached object context: ${trimmedCommand}`,
            action_params: meetingActionParams,
            mode: 'auto',
            stream: true,
            thread_id: activeMeetingId,
          });

      setLocalTasks((current) =>
        current.map((node) =>
          node.id === nextNodeId
            ? {
                ...node,
                detail: result?.async
                  ? selectedPackTool
                    ? `Accepted by ${selectedPackTool.label}. Awaiting execution events.`
                    : 'Accepted by the workspace runtime. Awaiting execution events.'
                  : selectedPackTool
                    ? `Instruction sent to ${selectedPackTool.label}.`
                    : 'Instruction sent to the meeting thread.',
                status: 'ready',
                output: result?.task_id ? `Task ID: ${result.task_id}` : 'Instruction dispatched.',
              }
            : node,
        ),
      );
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to dispatch meeting instruction.';
      setDispatchError(errorMessage);
      setLocalTasks((current) =>
        current.map((node) =>
          node.id === nextNodeId
            ? {
                ...node,
                detail: errorMessage,
                status: 'error',
                output: errorMessage,
              }
            : node,
        ),
      );
    }
  }

  return (
    <div
      className="flex h-full min-h-0 bg-slate-100 text-slate-900 dark:bg-slate-950 dark:text-slate-100"
      data-testid="aol-meeting-bottom-shell"
    >
      <div className="flex min-w-0 flex-1 flex-col">
        <MeetingHeaderToolbar
          activePanel={activeInfoPanel}
          activeMeetingId={activeMeetingId}
          sessionsCount={meetingSessions.length}
          sessionsLoading={meetingSessionsLoading}
          objectTitle={objectTitle}
          hasObjectContext={hasObjectContext}
          graphViewMode={graphViewMode}
          primaryCount={graphProjection.primaryCount}
          traceCount={graphProjection.traceCount}
          onTogglePanel={handleToggleInfoPanel}
          onGraphViewModeChange={handleGraphViewModeChange}
        />
        <div className="relative flex min-h-0 flex-1">
          {activeInfoPanel === 'object' ? (
            <div className="pointer-events-none absolute left-3 top-3 z-30 h-[calc(100%-1.5rem)] w-[min(340px,calc(100%-1.5rem))]">
              <MeetingObjectContextPanel
                summary={effectiveSummary}
                selection={effectiveSelection}
                attachResponse={effectiveAttachResponse}
                meetingId={activeMeetingId}
                surfaceRoute={surfaceRoute}
                onSwitchObject={onSwitchObject}
                onClose={() => {
                  setActiveInfoPanel(null);
                }}
              />
            </div>
          ) : null}
          {activeInfoPanel === 'sessions' ? (
            <div className="pointer-events-none absolute left-3 right-3 top-3 z-30 md:right-16">
              <MeetingSessionsPopover
                sessions={meetingSessions}
                activeMeetingId={activeMeetingId}
                loading={meetingSessionsLoading}
                error={meetingSessionsError}
                onSelectSession={(session) => {
                  setActiveMeetingId(session.id);
                  setSelectedNodeId('ready');
                  setIsConsoleOpen(false);
                  setActiveInfoPanel(null);
                }}
                onClose={() => {
                  setActiveInfoPanel(null);
                }}
              />
            </div>
          ) : null}
          <MeetingTaskCanvas
            nodes={nodes}
            selectedNodeId={selectedNodeId}
            onSelectNode={handleSelectNode}
            zoom={canvasZoom}
            onZoomIn={() => {
              handleCanvasZoom(CANVAS_ZOOM_STEP);
            }}
            onZoomOut={() => {
              handleCanvasZoom(-CANVAS_ZOOM_STEP);
            }}
            onResetView={() => {
              setCanvasZoom(1);
              setSelectedNodeId('ready');
            }}
            onWheelZoom={handleCanvasWheelZoom}
            commandImpact={selectedCommandImpact}
          />
        </div>
        {isConsoleOpen ? (
          <MeetingConsoleDrawer
            selectedNode={selectedNode}
            onClose={() => {
              setIsConsoleOpen(false);
            }}
          />
        ) : null}
        <MeetingCommandBar
          command={command}
          onCommandChange={setCommand}
          onSubmitCommand={handleSubmitCommand}
          isDispatching={isDispatching}
          isConsoleOpen={isConsoleOpen}
          onToggleConsole={() => {
            setIsConsoleOpen((current) => !current);
          }}
          packTools={packTools}
          selectedPackToolId={selectedPackToolId}
          onSelectedPackToolChange={setSelectedPackToolId}
          packToolsLoading={packToolsLoading}
          packToolsError={packToolsError}
          hasActiveMeeting={Boolean(activeMeetingId)}
          mentionItems={mentionItems}
          mentionItemsLoading={packToolsLoading || registryMentionItemsLoading}
          mentionItemsError={registryMentionItemsError}
          onApplyMention={handleApplyMention}
        />
        {dispatchError ? (
          <div className="border-t border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-300">
            {dispatchError}
          </div>
        ) : null}
      </div>

      <MeetingInspectorRail activeInspector={activeInspector} onToggleInspector={handleToggleInspector} />
      {activeInspector ? (
        <MeetingInspectorPanel
          activeInspector={activeInspector}
          selectedNode={selectedNode}
          runtimeSnapshot={runtimeSnapshot}
          workspaceId={workspaceId}
          apiUrl={apiUrl}
          meetingId={activeMeetingId}
          summary={effectiveSummary}
          attachResponse={effectiveAttachResponse}
          objectGraphProjections={objectGraphProjections}
          objectGraphLoading={objectGraphLoading}
          objectGraphError={objectGraphError}
          commandImpact={selectedCommandImpact}
          traceEvents={graphProjection.traceEvents}
          eventCounts={graphProjection.eventCounts}
          activeTraceFilter={activeTraceFilter}
          onTraceFilterChange={setActiveTraceFilter}
          onClose={() => {
            setActiveInspector(null);
          }}
        />
      ) : null}
    </div>
  );
}

export default AOLMeetingBottomShell;
