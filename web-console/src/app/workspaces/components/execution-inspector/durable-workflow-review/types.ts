export interface DurableWorkflowSummary {
  workflow_id: string;
  root_workflow_id: string;
  segment_id: string;
  segment_number: number;
  current_sequence: number;
  current_event_hash: string | null;
  current_state: string;
  terminal: boolean;
  next_durable_deadline: string | null;
  cancellation_state: string | null;
  workflow_definition_version: string;
  reducer_version: string;
  effect_adapter_registry_version: string;
  runtime_build_id: string;
  development_attestation_id: string;
  development_attestation_sha256: string;
  consumer_compatibility_class: string;
  configuration_fingerprint: string;
  environment_fingerprint: string;
  data_fingerprint: string;
  evidence_lifecycle: {
    manifest_id: string;
    evidence_class: string;
    lifecycle_action: string | null;
    reconciliation_state: string;
  } | null;
  checkpoint_count: number;
  open_approval_count: number;
  side_effect_count: number;
}

export interface DurableWorkflowEvent {
  event_id: string;
  workflow_id: string;
  sequence: number;
  event_type: string;
  occurred_at: string;
  event_hash: string;
  previous_event_hash: string | null;
  payload: Record<string, unknown>;
}

export interface DurableCheckpoint {
  checkpoint_id: string;
  workflow_id: string;
  segment_id: string;
  sequence: number;
  state_hash: string;
  event_hash: string;
  reducer_version: string;
  committed_at: string;
}

export interface AsOfSnapshot {
  workflow_id: string;
  sequence: number;
  event_hash: string | null;
  state: Record<string, unknown>;
  reducer_version: string;
  workflow_definition_version: string;
  effect_adapter_registry_version: string;
  runtime_build_id: string;
  replay_compatibility_class: string;
  development_attestation_id: string;
  development_attestation_sha256: string;
  consumer_compatibility_class: string;
  configuration_fingerprint: string;
  environment_fingerprint: string;
  data_fingerprint: string;
  effect_policy: 'receipts_only_no_direct_effect';
}
