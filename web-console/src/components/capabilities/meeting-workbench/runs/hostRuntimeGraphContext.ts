import type { AddressableObjectRef } from '@/lib/addressable-object-layer';

const DEFAULT_GRAPH_CONTEXT_BUDGET = {
  max_nodes: 16,
  max_edges: 32,
  max_prompt_chars: 4000,
};

export interface HostRuntimeGraphAnchor {
  anchor_uri: string;
  ref: AddressableObjectRef;
  owner_pack: string;
  object_kind: string;
  object_id: string;
}

export interface HostRuntimeGraphSelectionRef {
  kind: 'GraphSelection';
  workspace_id: string;
  meeting_id: string | null;
  anchor_uri: string | null;
  selected_ref_uris: string[];
  selection_hash: string;
  selector_scope: 'anchored_object_neighborhood' | 'workspace_meeting';
  status: 'anchored' | 'empty_anchor';
}

export interface HostRuntimeGraphContextRef {
  kind: 'SubgraphContext';
  context_id: string;
  workspace_id: string;
  meeting_id: string | null;
  graph_selection_hash: string;
}

export interface HostRuntimeObjectGraphAggregateUnit {
  kind: 'ObjectGraphAggregateUnit';
  unit_id: string;
  owner_pack: string | null;
  anchor_uri: string | null;
  node_count: number;
  edge_count: number;
  budget: typeof DEFAULT_GRAPH_CONTEXT_BUDGET;
  truncation: {
    truncated: boolean;
    reason: string | null;
  };
  snapshot_hash: string;
  provenance_refs: string[];
}

export interface HostRuntimeGraphSnapshotSummary {
  snapshot_hash: string;
  node_count: number;
  edge_count: number;
  owner_packs: string[];
  truncated: boolean;
  budget: typeof DEFAULT_GRAPH_CONTEXT_BUDGET;
  provenance_refs: string[];
}

export interface HostRuntimeGraphContext {
  context_contract_version: 'aol_graph_context_v1';
  source: 'aol_graph_runtime_runs';
  meeting_id: string | null;
  selected_graph_anchor: HostRuntimeGraphAnchor | null;
  graph_selection_ref: HostRuntimeGraphSelectionRef;
  graph_context_ref: HostRuntimeGraphContextRef;
  graph_snapshot_summary: HostRuntimeGraphSnapshotSummary;
  object_graph_aggregate_unit: HostRuntimeObjectGraphAggregateUnit;
  selected_object_ref?: AddressableObjectRef | null;
}

function stableSerialize(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(stableSerialize).join(',')}]`;
  }
  if (value && typeof value === 'object') {
    return `{${Object.keys(value as Record<string, unknown>)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableSerialize((value as Record<string, unknown>)[key])}`)
      .join(',')}}`;
  }
  return JSON.stringify(value);
}

function compactHash(value: unknown): string {
  const serialized = stableSerialize(value);
  let hash = 0x811c9dc5;
  for (let index = 0; index < serialized.length; index += 1) {
    hash ^= serialized.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

function buildGraphAnchor(selectedObjectRef: AddressableObjectRef | null): HostRuntimeGraphAnchor | null {
  if (!selectedObjectRef) {
    return null;
  }
  return {
    anchor_uri: selectedObjectRef.uri,
    ref: selectedObjectRef,
    owner_pack: selectedObjectRef.owner_pack,
    object_kind: selectedObjectRef.object_kind,
    object_id: selectedObjectRef.object_id,
  };
}

export function buildHostRuntimeGraphContext({
  workspaceId,
  meetingId,
  selectedObjectRef,
}: {
  workspaceId: string;
  meetingId: string | null;
  selectedObjectRef: AddressableObjectRef | null;
}): HostRuntimeGraphContext {
  const selectedGraphAnchor = buildGraphAnchor(selectedObjectRef);
  const selectedRefUris = selectedGraphAnchor ? [selectedGraphAnchor.anchor_uri] : [];
  const selectionHash = `gsel_${compactHash({
    workspaceId,
    meetingId,
    selectedRefUris,
    source: 'aol_graph_runtime_runs',
  })}`;
  const snapshotHash = `ogau_${compactHash({
    workspaceId,
    meetingId,
    selectionHash,
    selectedObjectRef,
    budget: DEFAULT_GRAPH_CONTEXT_BUDGET,
  })}`;
  const provenanceRefs = selectedGraphAnchor
    ? [`selected_graph_anchor:${selectedGraphAnchor.anchor_uri}`]
    : ['selected_graph_anchor:none'];
  const graphSelectionRef: HostRuntimeGraphSelectionRef = {
    kind: 'GraphSelection',
    workspace_id: workspaceId,
    meeting_id: meetingId,
    anchor_uri: selectedGraphAnchor?.anchor_uri ?? null,
    selected_ref_uris: selectedRefUris,
    selection_hash: selectionHash,
    selector_scope: selectedGraphAnchor ? 'anchored_object_neighborhood' : 'workspace_meeting',
    status: selectedGraphAnchor ? 'anchored' : 'empty_anchor',
  };
  const graphContextRef: HostRuntimeGraphContextRef = {
    kind: 'SubgraphContext',
    context_id: `gctx_${compactHash({ workspaceId, meetingId, selectionHash, snapshotHash })}`,
    workspace_id: workspaceId,
    meeting_id: meetingId,
    graph_selection_hash: selectionHash,
  };
  const objectGraphAggregateUnit: HostRuntimeObjectGraphAggregateUnit = {
    kind: 'ObjectGraphAggregateUnit',
    unit_id: snapshotHash,
    owner_pack: selectedGraphAnchor?.owner_pack ?? null,
    anchor_uri: selectedGraphAnchor?.anchor_uri ?? null,
    node_count: selectedGraphAnchor ? 1 : 0,
    edge_count: 0,
    budget: DEFAULT_GRAPH_CONTEXT_BUDGET,
    truncation: {
      truncated: false,
      reason: null,
    },
    snapshot_hash: snapshotHash,
    provenance_refs: provenanceRefs,
  };

  return {
    context_contract_version: 'aol_graph_context_v1',
    source: 'aol_graph_runtime_runs',
    meeting_id: meetingId,
    selected_graph_anchor: selectedGraphAnchor,
    graph_selection_ref: graphSelectionRef,
    graph_context_ref: graphContextRef,
    graph_snapshot_summary: {
      snapshot_hash: snapshotHash,
      node_count: objectGraphAggregateUnit.node_count,
      edge_count: objectGraphAggregateUnit.edge_count,
      owner_packs: selectedGraphAnchor ? [selectedGraphAnchor.owner_pack] : [],
      truncated: objectGraphAggregateUnit.truncation.truncated,
      budget: objectGraphAggregateUnit.budget,
      provenance_refs: provenanceRefs,
    },
    object_graph_aggregate_unit: objectGraphAggregateUnit,
    selected_object_ref: selectedObjectRef,
  };
}
