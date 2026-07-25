import type { UIComponentInfo } from '@/lib/capability-ui-loader';

export interface ProductArm {
  arm_id: string;
  development_attestation_id: string;
  development_attestation_sha256: string;
  consumer_compatibility_class: string;
  capability_identity: {
    capability_code: string;
    pack_version: string;
    manifest_sha256: string;
  };
  configuration_fingerprint: string;
  environment_fingerprint: string;
  data_fingerprint: string;
  consumer_impact_manifest_sha256: string;
  allocation_weight: number;
}

export interface GateResult {
  gate_id: string;
  status: 'pass' | 'fail' | 'inconclusive' | 'missing';
  evidence_hash: string;
}

export interface ReviewLensPin {
  capability_code: string;
  pack_version: string;
  manifest_sha256: string;
  descriptor_sha256: string;
  component_code: string;
  integrity: string;
  runtime: 'esm';
  export: string;
}

export interface ProductIterationReviewSummary {
  iteration_id: string;
  workspace_id: string;
  current_sequence: number;
  current_event_hash: string | null;
  state: string;
  terminal: boolean;
  objective: string;
  revision: number;
  parent_iteration_id: string | null;
  definition_sha256: string;
  arms: ProductArm[];
  selected_arm_id: string;
  validation_design: Record<string, unknown>;
  evaluator: {
    evaluator_id: string;
    version: string;
    contract_hash: string;
  };
  metric_definitions: Array<{
    metric_id: string;
    direction: string;
    denominator_definition: string;
    quality_gate: string;
  }>;
  evidence_frontier: {
    last_observation_sequence: number;
    frontier_hash: string;
    accepted_observation_count: number;
    minimum_sample_size: number;
  };
  evaluation_attempt_count: number;
  evaluation: {
    evaluation_id: string;
    evaluation_attempt_id: string;
    recommendation: string;
    decision: string;
    source_observation_ref: ObjectReference;
    evaluated_at: string;
  } | null;
  gate_results: GateResult[];
  governance_receipts: {
    approval_request: Record<string, unknown> | null;
    approval_decision: Record<string, unknown> | null;
    approval_consumption: Record<string, unknown> | null;
    release_effect: Record<string, unknown> | null;
  };
  product_release: {
    state: string;
    terminal?: boolean;
    release_workflow_id: string | null;
    release_link?: Record<string, unknown> | null;
    health?: Record<string, unknown> | null;
    lifecycle?: EvidenceLifecycle | null;
  };
  evidence_lifecycle: EvidenceLifecycle | null;
  experience_summary: {
    claims: Array<{
      claim_id: string;
      kind: string;
      text: string;
      source_observation_ids: string[];
      provenance_sha256: string;
    }>;
    projection_sha256: string;
    authority: 'projection_only';
  } | null;
  review_lens: ReviewLensPin | null;
  effect_policy: 'read_only_no_effect';
}

export interface ObjectReference {
  uri: string;
  sha256: string;
  bytes: number;
  schema_id: string;
}

export interface EvidenceLifecycle {
  manifest_id: string;
  evidence_class: string;
  content_hash: string;
  object_ref: ObjectReference;
  privacy_classification: string;
  legal_hold: boolean;
  lifecycle_action: string | null;
  reconciliation_state: string;
}

export interface AsOfProductIteration {
  iteration_id: string;
  sequence: number;
  event_hash: string | null;
  state: Record<string, unknown>;
  reducer_version: string;
  effect_policy: 'read_only_no_effect';
}

export interface ProductIterationComparison {
  status: 'comparable' | 'incomparable';
  comparable: boolean;
  reason_codes: string[];
  delta: {
    accepted_observation_count: number;
    gate_status_changes: Record<
      string,
      { left: string; right: string }
    >;
  } | null;
}

export interface ReviewLensSelection {
  component: UIComponentInfo;
  pin: ReviewLensPin;
}
