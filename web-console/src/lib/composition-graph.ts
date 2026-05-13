import { buildApiUrls, fetchApiJson, postApiJson } from '@/components/capabilities/meeting-workbench/meetingApi';

export type CompositionGraphPortDirection = 'input' | 'output';
export type CompositionGraphDiagnosticSeverity = 'error' | 'warning' | 'info';
export type CompositionGraphCompileStatus = 'succeeded' | 'failed';

export interface CompositionGraphViewport {
  x: number;
  y: number;
  zoom: number;
}

export interface CompositionGraphPort {
  id: string;
  direction: CompositionGraphPortDirection;
  label?: string | null;
  data_type: string;
  required?: boolean;
  accepted_object_roles?: string[];
  metadata?: Record<string, unknown>;
}

export interface CompositionGraphNodeType {
  id: string;
  label: string;
  source: 'core' | 'pack';
  capability_code?: string | null;
  description?: string | null;
  category?: string | null;
  input_ports?: CompositionGraphPort[];
  output_ports?: CompositionGraphPort[];
  payload_schema?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

export interface CompositionGraphEdgeType {
  id: string;
  label: string;
  source_data_type?: string;
  target_data_type?: string;
  metadata?: Record<string, unknown>;
}

export interface CompositionGraphCompileTarget {
  backend: string;
  output_mode: 'meeting_command_envelope';
}

export interface CompositionGraphContract {
  capability_code: string;
  label: string;
  enabled: boolean;
  contract_version: string;
  accepted_object_roles?: string[];
  node_types: CompositionGraphNodeType[];
  edge_types: CompositionGraphEdgeType[];
  compile: CompositionGraphCompileTarget;
  metadata?: Record<string, unknown>;
}

export interface CompositionGraphDiagnostic {
  code: string;
  message: string;
  severity: CompositionGraphDiagnosticSeverity;
  node_id?: string | null;
  edge_id?: string | null;
  port_id?: string | null;
  metadata?: Record<string, unknown>;
}

export interface CompositionGraphNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  payload: Record<string, unknown>;
  capability_code?: string | null;
  metadata?: Record<string, unknown>;
}

export interface CompositionGraphEdge {
  id: string;
  source: string;
  target: string;
  source_port: string;
  target_port: string;
  type: string;
  metadata?: Record<string, unknown>;
}

export interface CompositionGraphDraft {
  id: string;
  graph_id: string;
  workspace_id: string;
  title: string;
  schema_version: string;
  meeting_id?: string | null;
  thread_id?: string | null;
  selected_primary_pack?: string | null;
  nodes: CompositionGraphNode[];
  edges: CompositionGraphEdge[];
  viewport: CompositionGraphViewport;
  history?: unknown[];
  migrations?: unknown[];
  node_diagnostics?: Record<string, CompositionGraphDiagnostic[]>;
  edge_diagnostics?: Record<string, CompositionGraphDiagnostic[]>;
  metadata?: Record<string, unknown>;
}

export interface CompositionGraphImportExportPayload {
  schema_version: string;
  graph_id: string;
  title: string;
  selected_primary_pack?: string | null;
  nodes: CompositionGraphNode[];
  edges: CompositionGraphEdge[];
  viewport: CompositionGraphViewport;
  metadata?: Record<string, unknown>;
}

export interface CompositionGraphCommandEnvelopeDraft {
  meeting_id: string;
  intent_text: string;
  thread_id?: string | null;
  context_objects?: unknown[];
  meeting_mentions?: Record<string, unknown>[];
  requested_action?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

export interface CompositionGraphCompileResponse {
  workspace_id: string;
  status: CompositionGraphCompileStatus;
  output_mode: 'meeting_command_envelope';
  diagnostics: CompositionGraphDiagnostic[];
  command_envelope?: CompositionGraphCommandEnvelopeDraft | null;
  metadata?: Record<string, unknown>;
}

export interface CompositionGraphContractsResponse {
  workspace_id: string;
  contracts: CompositionGraphContract[];
  diagnostics: CompositionGraphDiagnostic[];
}

export interface CompositionGraphDraftResponse {
  workspace_id: string;
  draft: CompositionGraphDraft;
}

export interface CompositionGraphImportResponse {
  workspace_id: string;
  valid: boolean;
  diagnostics: CompositionGraphDiagnostic[];
  draft?: CompositionGraphDraft | null;
}

export interface CompositionGraphDraftMutation {
  title?: string;
  meeting_id?: string | null;
  thread_id?: string | null;
  selected_primary_pack?: string | null;
  nodes: CompositionGraphNode[];
  edges: CompositionGraphEdge[];
  viewport: CompositionGraphViewport;
  metadata?: Record<string, unknown>;
}

export interface CompositionGraphCompileRequest {
  graph_id?: string;
  draft_id?: string;
  meeting_id: string;
  thread_id?: string | null;
  command: string;
  selected_primary_pack?: string | null;
  nodes?: CompositionGraphNode[];
  edges?: CompositionGraphEdge[];
  viewport?: CompositionGraphViewport;
  meeting_mentions?: Record<string, unknown>[];
  context_objects?: unknown[];
  object_action_entries?: unknown[];
  selected_pack_tool?: string | null;
  action_parameters?: Record<string, unknown>;
}

export async function fetchCompositionGraphContracts(
  apiUrl: string,
  workspaceId: string,
): Promise<CompositionGraphContractsResponse> {
  const payload = await fetchApiJson(
    apiUrl,
    `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/composition-graph/contracts`,
  );
  return payload as CompositionGraphContractsResponse;
}

export async function createCompositionGraphDraft(
  apiUrl: string,
  workspaceId: string,
  draft: CompositionGraphDraftMutation,
): Promise<CompositionGraphDraftResponse> {
  const payload = await postApiJson(
    apiUrl,
    `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/composition-graph/drafts`,
    draft,
  );
  return payload as CompositionGraphDraftResponse;
}

export async function updateCompositionGraphDraft(
  apiUrl: string,
  workspaceId: string,
  draftId: string,
  draft: CompositionGraphDraftMutation,
): Promise<CompositionGraphDraftResponse> {
  let lastError: unknown = null;
  for (const url of buildApiUrls(
    apiUrl,
    `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/composition-graph/drafts/${encodeURIComponent(draftId)}`,
  )) {
    try {
      const response = await fetch(url, {
        method: 'PUT',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
      });
      if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
      }
      return (await response.json()) as CompositionGraphDraftResponse;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError instanceof Error ? lastError : new Error('Request failed');
}

export async function importCompositionGraph(
  apiUrl: string,
  workspaceId: string,
  graph: CompositionGraphImportExportPayload,
  options: { meetingId?: string | null; threadId?: string | null; persist?: boolean } = {},
): Promise<CompositionGraphImportResponse> {
  const payload = await postApiJson(
    apiUrl,
    `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/composition-graph/import`,
    {
      graph,
      meeting_id: options.meetingId,
      thread_id: options.threadId,
      persist: options.persist ?? false,
    },
  );
  return payload as CompositionGraphImportResponse;
}

export async function compileCompositionGraph(
  apiUrl: string,
  workspaceId: string,
  request: CompositionGraphCompileRequest,
): Promise<CompositionGraphCompileResponse> {
  const payload = await postApiJson(
    apiUrl,
    `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/composition-graph/compile`,
    request,
  );
  return payload as CompositionGraphCompileResponse;
}
