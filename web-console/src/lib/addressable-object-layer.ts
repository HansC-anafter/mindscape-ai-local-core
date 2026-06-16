export type AddressableObjectRole =
  | 'source'
  | 'target'
  | 'baseline'
  | 'constraint'
  | 'evidence';

export type AddressableObjectHostMode =
  | 'idle'
  | 'selecting'
  | 'resolving'
  | 'disambiguating'
  | 'selected'
  | 'attaching'
  | 'meeting_opened'
  | 'error';

export interface AddressableSelectionTarget {
  ownerPack: string;
  objectKind: string;
  objectId: string;
  version?: string;
  selector?: Record<string, unknown>;
  sourceSurface?: string;
  elementId?: string;
  label?: string;
  role?: AddressableObjectRole;
}

export type AddressableGraphSelectionKind =
  | 'anchor'
  | 'multi_anchor'
  | 'path'
  | 'subgraph'
  | 'projection'
  | 'weighted';

export interface AddressableGraphSelectionBudget {
  max_nodes: number;
  max_edges: number;
  max_prompt_chars: number;
}

export interface AddressableGraphSelectionAnchor {
  ref?: AddressableObjectRef | null;
  uri: string;
  owner_pack: string;
  object_kind: string;
  object_id: string;
  workspace_id?: string | null;
  selector?: Record<string, unknown> | null;
  source_surface?: string | null;
  label?: string | null;
  role?: AddressableObjectRole | null;
}

export interface AddressableGraphSelection {
  owner_pack: string;
  selection_kind: AddressableGraphSelectionKind;
  anchors: AddressableGraphSelectionAnchor[];
  lens_code: string;
  relation_scope: string[];
  node_limit: number;
  relation_limit: number;
  snapshot_budget: AddressableGraphSelectionBudget;
  source_surface: string;
  governance_tags: string[];
  user_intent?: string | null;
  selection_hash?: string | null;
}

export interface AddressableObjectHostBridge {
  mode: AddressableObjectHostMode;
  selection: AddressableSelectionTarget | null;
  graphSelection?: AddressableGraphSelection | null;
  currentMeetingId: string | null;
  requestObjectTargeting: () => void;
  cancelObjectTargeting: () => void;
  onSelectObject: (selection: AddressableSelectionTarget) => void | Promise<void>;
  onSelectGraph?: (selection: AddressableGraphSelection) => void | Promise<void>;
  clearCurrentObject: () => void;
  openCurrentMeeting: () => void;
}

export interface AddressableObjectRef {
  uri: string;
  owner_pack: string;
  object_kind: string;
  object_id: string;
  workspace_id?: string | null;
  version?: string | null;
  selector?: Record<string, unknown> | null;
  source_surface?: string | null;
}

export interface AddressableObjectSummary {
  ref: AddressableObjectRef;
  title: string;
  subtitle?: string | null;
  summary_text?: string | null;
  status?: string | null;
  labels: string[];
  thumbnail_ref?: string | null;
  owner_surface_url?: string | null;
  updated_at?: string | null;
}

export interface AddressableObjectAction {
  action_code: string;
  label: string;
  description: string;
  verb: string;
  mode: string;
  requires_review?: boolean;
  target_kind?: string | null;
}

export interface AddressableRuntimeError {
  code: string;
  message: string;
}

export interface ResolvedAddressableObject {
  ref: AddressableObjectRef;
  summary: AddressableObjectSummary;
  actions: AddressableObjectAction[];
}

export interface AddressableSelectionCandidate {
  ref: AddressableObjectRef;
  summary?: AddressableObjectSummary | null;
}

export interface SelectionResolveResponse {
  workspace_id: string;
  selection_id: string;
  status: 'resolved' | 'ambiguous' | 'unresolved';
  resolved_objects: ResolvedAddressableObject[];
  candidate_objects: AddressableSelectionCandidate[];
  errors: AddressableRuntimeError[];
}

export interface ObjectMeetingAttachResponse {
  workspace_id: string;
  meeting_id: string;
  status: 'attached' | 'materialized' | 'rejected';
  attachments: Array<{
    role: AddressableObjectRole;
    ref: AddressableObjectRef;
    projection_level: 'summary' | 'meeting';
  }>;
  target_ref?: AddressableObjectRef | null;
  staged_refs: AddressableObjectRef[];
  review_routes: string[];
  errors: AddressableRuntimeError[];
}

export interface ObjectGraphRelation {
  relation_kind: string;
  direction: 'outbound' | 'inbound' | 'bidirectional';
  target_ref: AddressableObjectRef;
  metadata?: Record<string, unknown>;
}

export interface ObjectGuidanceCard {
  id: string;
  title: string;
  description?: string | null;
  intent?: string | null;
  command_template?: string | null;
  review_label?: string | null;
  review_routes?: string[];
  proposal_ref?: AddressableObjectRef | null;
  target_ref?: AddressableObjectRef | null;
  required_roles?: string[];
  priority?: number;
  metadata?: Record<string, unknown>;
}

export interface ObjectGraphProjection {
  ref: AddressableObjectRef;
  summary?: AddressableObjectSummary | null;
  node_kind?: string | null;
  relations: ObjectGraphRelation[];
  guidance?: ObjectGuidanceCard[];
  metadata?: Record<string, unknown>;
}

export interface ObjectGraphProjectResponse {
  workspace_id: string;
  projections: ObjectGraphProjection[];
  errors: AddressableRuntimeError[];
}

interface ResolveAddressableSelectionParams {
  apiUrl: string;
  workspaceId: string;
  capabilityCode: string;
  route: string;
  surfaceId: string;
  selection: AddressableSelectionTarget;
}

interface AttachAddressableObjectParams {
  apiUrl: string;
  workspaceId: string;
  resolvedObject: ResolvedAddressableObject;
  role?: AddressableObjectRole;
  meetingType?: string;
  writeMode?: 'proposal_only' | 'staged' | 'recommendation_only';
  intentSummary?: string;
}

interface ProjectAddressableObjectGraphParams {
  apiUrl: string;
  workspaceId: string;
  objects: AddressableObjectRef[];
  includeRelations?: boolean;
  includeSummaries?: boolean;
}

function createRuntimeId(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}`;
}

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};

  if (!response.ok) {
    const detail = typeof payload?.detail === 'string'
      ? payload.detail
      : typeof payload?.detail?.message === 'string'
        ? payload.detail.message
        : text || `HTTP ${response.status}`;
    throw new Error(detail);
  }

  return payload as T;
}

export async function resolveAddressableSelection({
  apiUrl,
  workspaceId,
  capabilityCode,
  route,
  surfaceId,
  selection,
}: ResolveAddressableSelectionParams): Promise<SelectionResolveResponse> {
  const payload = {
    selection_id: createRuntimeId('sel'),
    surface: {
      surface_type: 'pack_ui',
      pack_code: capabilityCode,
      surface_id: surfaceId,
      route,
    },
    element: selection.elementId || selection.label
      ? {
          element_id: selection.elementId ?? null,
          label: selection.label ?? null,
        }
      : undefined,
    hints: {
      owner_pack: selection.ownerPack,
      object_kind: selection.objectKind,
      object_id: selection.objectId,
      version: selection.version,
      selector: selection.selector,
      source_surface: selection.sourceSurface ?? surfaceId,
    },
    mode: 'contextual_actions',
  };

  const response = await fetch(
    `${apiUrl}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/selection/resolve`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  );

  return parseJsonOrThrow<SelectionResolveResponse>(response);
}

export async function attachAddressableObjectToMeeting({
  apiUrl,
  workspaceId,
  resolvedObject,
  role = 'source',
  meetingType = 'direction',
  writeMode = 'proposal_only',
  intentSummary,
}: AttachAddressableObjectParams): Promise<ObjectMeetingAttachResponse> {
  const payload = {
    meeting_type: meetingType,
    meeting_id: null,
    entries: [
      {
        role,
        ref: resolvedObject.ref,
      },
    ],
    intent_summary: intentSummary ?? `Bring ${resolvedObject.summary.title} into a direction meeting.`,
    write_mode: writeMode,
  };

  const response = await fetch(
    `${apiUrl}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/object-meeting-attach`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  );

  return parseJsonOrThrow<ObjectMeetingAttachResponse>(response);
}

export async function projectAddressableObjectGraph({
  apiUrl,
  workspaceId,
  objects,
  includeRelations = true,
  includeSummaries = true,
}: ProjectAddressableObjectGraphParams): Promise<ObjectGraphProjectResponse> {
  const response = await fetch(
    `${apiUrl}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/object-graph/project`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        objects,
        include_relations: includeRelations,
        include_summaries: includeSummaries,
      }),
    },
  );

  return parseJsonOrThrow<ObjectGraphProjectResponse>(response);
}

export function buildCanonicalMeetingRoute(workspaceId: string, meetingId: string): string {
  const params = new URLSearchParams({ session_id: meetingId });
  return `/workspaces/${encodeURIComponent(workspaceId)}/meetings?${params.toString()}`;
}
