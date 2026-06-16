export interface ModelRouteSlot {
  slot_id: string;
  slot_kind: string;
  title: string;
  summary: string;
  source: string;
  settings_anchor?: string | null;
  evidence_path?: string | null;
}

export interface PackCoverageEntry {
  pack_id: string;
  name: string;
  installed: boolean;
  enabled: boolean;
  slot_count: number;
  live_slot_count: number;
  stored_slot_count: number;
  registration_drift: boolean;
  slot_kinds: string[];
}

export interface PackGroup {
  pack_id: string;
  name: string;
  slot_count: number;
  registration_drift: boolean;
  slot_kinds: string[];
  slots: ModelRouteSlot[];
}

export interface RuntimeGroup {
  runtime_id: string;
  name: string;
  status: string;
  slot_count: number;
  stored_slot_count?: number;
  registration_drift?: boolean;
  slots: ModelRouteSlot[];
}

export interface RoutingPolicyItem {
  key: string;
  label: string;
  summary: string;
  active: boolean;
}

export interface RoutingPolicyPayload {
  route_authority: string;
  precedence: RoutingPolicyItem[];
  workspace_override: {
    enabled: boolean;
    summary: string;
  };
  fallback_policy: {
    allowed: boolean;
    mode: string;
    summary: string;
  };
}

export interface ModelRouteRegistryPayload {
  summary: {
    total_slot_count: number;
    local_core_slot_count: number;
    installed_pack_count_scanned: number;
    installed_pack_count_with_slots: number;
    installed_pack_slot_count: number;
    registered_runtime_count: number;
    registered_runtime_slot_count: number;
    packs_with_registration_drift: string[];
  };
  local_core_slots: ModelRouteSlot[];
  pack_groups: PackGroup[];
  pack_coverage: PackCoverageEntry[];
  registered_runtimes: RuntimeGroup[];
  policy?: RoutingPolicyPayload;
  executor_policy?: RoutingPolicyPayload;
}

export interface ReconcileResult {
  updated_pack_count: number;
  updated_runtime_count: number;
}
