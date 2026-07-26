import { getApiBaseUrl } from './api-url';

export type WorkspaceProductAdmissionMode =
  | 'legacy_unmanaged'
  | 'configuration_only'
  | 'shadow'
  | 'enforced';
export type WorkspaceProductScopeKind = 'workspace' | 'workspace_group';

export interface ProductAssignment {
  pcs_id: string;
  pcs_version: string;
}

export interface ScopeConfiguration {
  scope_kind: WorkspaceProductScopeKind;
  scope_id: string;
  catalog_hash?: string | null;
  revision: number;
  admission_mode?: WorkspaceProductAdmissionMode | null;
  assignments: ProductAssignment[];
  editable: boolean;
}

export interface ProductClosureSummary {
  total_packs: number;
  exact_ready_packs: number;
  missing_packs: number;
  disabled_packs: number;
  version_mismatch_packs: number;
}

export interface AvailableProduct {
  pcs_id: string;
  exact_version: string;
  display_name: string;
  outcome_summary: string;
  surface_ids: string[];
  product_surfaces: Array<{
    id: string;
    display_name: string;
    selectors: {
      api_prefixes: string[];
      tool_prefixes: string[];
      tool_keys: string[];
      playbook_codes: string[];
      ui_routes: string[];
    };
  }>;
  closure_summary: ProductClosureSummary;
  pack_closure: Array<{
    provider: string;
    code: string;
    version: string;
    readiness: 'ready' | 'missing' | 'disabled' | 'version_mismatch';
  }>;
}

export interface EffectiveProductAssignment {
  pcs_id: string;
  pcs_version: string;
  product_surface_ids: string[];
  configuration_sources: WorkspaceProductScopeKind[];
  host_ready: boolean;
  host_admission: ProductHostAdmissionDetail[];
}

export interface ProductHostAdmissionDetail {
  pack_code: string;
  requirement_code: string;
  operation: string;
  admitted: boolean;
  binding_id?: string | null;
  binding_generation?: number | null;
  grant_id?: string | null;
  attestation_revision?: number | null;
  policy_revision?: number | null;
  blockers: string[];
}

export interface WorkspaceCapabilitySetSnapshot {
  source_runtime_id: string;
  workspace_id: string;
  explicit_active_group_id?: string | null;
  topology_revision?: number | null;
  topology_content_hash?: string | null;
  catalog_hash: string;
  snapshot_hash: string;
  workspace_scope_revision: number;
  group_scope_revision: number;
  workspace_admission_mode: WorkspaceProductAdmissionMode;
  editable_scopes: WorkspaceProductScopeKind[];
  scope_configurations: ScopeConfiguration[];
  available_products: AvailableProduct[];
  effective_assignments: EffectiveProductAssignment[];
  configuration_errors: string[];
  deployment_control?: {
    mode: 'unmanaged_local' | 'provider_managed';
    provider_code?: string | null;
    state_revision: number;
    envelope_revision?: number | null;
    envelope_hash?: string | null;
    permitted_surface_ids: string[];
  } | null;
}

export interface ReplaceWorkspaceProductConfiguration {
  expected_revision: number;
  assignments: ProductAssignment[];
  admission_mode?: Exclude<WorkspaceProductAdmissionMode, 'legacy_unmanaged'>;
  catalog_hash: string;
}

export class WorkspaceProductApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    super(`workspace_product_request_failed:${status}`);
    this.status = status;
    this.detail = detail;
  }
}

function baseUrl(): string {
  return getApiBaseUrl().replace(/\/+$/, '');
}

function contextQuery(
  activeGroupId?: string | null,
  topologyRevision?: number | null,
): string {
  const query = new URLSearchParams();
  if (activeGroupId) query.set('active_group_id', activeGroupId);
  if (topologyRevision) {
    query.set('observed_topology_revision', String(topologyRevision));
  }
  const encoded = query.toString();
  return encoded ? `?${encoded}` : '';
}

async function readSnapshot(response: Response): Promise<WorkspaceCapabilitySetSnapshot> {
  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    throw new WorkspaceProductApiError(response.status, payload);
  }
  return payload as WorkspaceCapabilitySetSnapshot;
}

export async function getEffectiveWorkspaceProductConfiguration({
  workspaceId,
  activeGroupId,
  topologyRevision,
  signal,
}: {
  workspaceId: string;
  activeGroupId?: string | null;
  topologyRevision?: number | null;
  signal?: AbortSignal;
}): Promise<WorkspaceCapabilitySetSnapshot> {
  const path = (
    `/api/v1/workspaces/${encodeURIComponent(workspaceId)}`
    + '/product-configuration/effective'
    + contextQuery(activeGroupId, topologyRevision)
  );
  const response = await fetch(`${baseUrl()}${path}`, {
    cache: 'no-store',
    credentials: 'same-origin',
    signal,
  });
  return readSnapshot(response);
}

export async function replaceWorkspaceProductConfiguration({
  workspaceId,
  activeGroupId,
  topologyRevision,
  scopeKind,
  command,
  signal,
}: {
  workspaceId: string;
  activeGroupId?: string | null;
  topologyRevision?: number | null;
  scopeKind: WorkspaceProductScopeKind;
  command: ReplaceWorkspaceProductConfiguration;
  signal?: AbortSignal;
}): Promise<WorkspaceCapabilitySetSnapshot> {
  const path = scopeKind === 'workspace'
    ? (
        `/api/v1/workspaces/${encodeURIComponent(workspaceId)}`
        + '/product-configuration'
        + contextQuery(activeGroupId, topologyRevision)
      )
    : (
        `/api/v1/workspace-groups/${encodeURIComponent(activeGroupId || '')}`
        + '/product-configuration?'
        + new URLSearchParams({
          workspace_id: workspaceId,
          ...(topologyRevision
            ? { observed_topology_revision: String(topologyRevision) }
            : {}),
        }).toString()
      );
  const response = await fetch(`${baseUrl()}${path}`, {
    method: 'PUT',
    cache: 'no-store',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(command),
    signal,
  });
  return readSnapshot(response);
}
