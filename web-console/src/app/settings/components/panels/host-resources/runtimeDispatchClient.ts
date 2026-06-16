import { settingsApi } from '../../../utils/settingsApi';

export interface RuntimeDispatchFeatureGate {
  enabled: boolean;
  env_var?: string;
  default_enabled?: boolean;
  reason?: string | null;
}

export interface RuntimeDispatchSelectorType {
  selector_type: string;
  label?: string;
  workspace_scope_required?: boolean;
  max_items?: number;
  supports_preview?: boolean;
  supports_apply?: boolean;
}

export interface RuntimeDispatchTarget {
  target_id?: string;
  lane_id?: string;
  label?: string;
  workspace_id?: string | null;
  capability_scope?: string | null;
  queue_shard?: string | null;
  runner_profile?: string | null;
  resource_class?: string | null;
  state?: string | null;
  assignable?: boolean;
  assignability_reason?: string | null;
  capacity_summary?: {
    source?: string | null;
    claimable_runner_count?: number | null;
    active_runner_count?: number | null;
    available_slots_total?: number | null;
    pending?: number | null;
    processing?: number | null;
  };
}

export interface RuntimeDispatchSelectorTypesPayload {
  feature_gate?: RuntimeDispatchFeatureGate;
  selector_types?: RuntimeDispatchSelectorType[];
  limits?: {
    max_items?: number;
    requires_workspace_access?: boolean;
    allows_cross_workspace_refs?: boolean;
  };
}

export interface RuntimeDispatchTargetsPayload {
  feature_gate?: RuntimeDispatchFeatureGate;
  workspace_id?: string;
  targets?: RuntimeDispatchTarget[];
  count?: number;
  metadata_source?: string;
  queue_utilization_source?: string | null;
  degraded?: boolean;
  errors?: unknown[];
}

export interface RuntimeDispatchMetadata {
  selectors: RuntimeDispatchSelectorTypesPayload;
  targets: RuntimeDispatchTargetsPayload;
}

export async function loadRuntimeDispatchMetadata(
  workspaceId: string,
): Promise<RuntimeDispatchMetadata> {
  const workspaceQuery = encodeURIComponent(workspaceId);
  const [selectors, targets] = await Promise.all([
    settingsApi.get<RuntimeDispatchSelectorTypesPayload>('/api/v1/runtime-dispatch/selector-types'),
    settingsApi.get<RuntimeDispatchTargetsPayload>(
      `/api/v1/runtime-dispatch/targets?workspace_id=${workspaceQuery}`,
    ),
  ]);
  return { selectors, targets };
}
