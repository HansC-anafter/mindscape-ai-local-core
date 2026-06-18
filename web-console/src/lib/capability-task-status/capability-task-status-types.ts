export const CAPABILITY_TASK_STATUS_EVENT = 'mindscape:capability_task_status' as const;

export type CapabilityTaskStatusValue =
  | 'submitted'
  | 'accepted'
  | 'queued'
  | 'running'
  | 'existing'
  | 'satisfied'
  | 'confirmed'
  | 'succeeded'
  | 'failed'
  | 'operator_review';

export interface CapabilityTaskStatusTarget {
  kind: string;
  key: string;
  label?: string;
}

export interface CapabilityTaskStatusEnvelope {
  schemaVersion: 'capability_task_status.v1';
  workspaceId: string;
  capabilityCode: string;
  actionId: string;
  status: CapabilityTaskStatusValue;
  submissionId?: string;
  statusUrl?: string;
  executionId?: string;
  executionIds?: string[];
  playbookCode?: string;
  target?: CapabilityTaskStatusTarget;
  submittedAt?: string;
  updatedAt?: string;
  source?: string;
  metadata?: Record<string, unknown>;
  ttlMs?: number;
}

export interface CapabilityTaskStatusReceipt {
  key: string;
  emitted: boolean;
  duplicate: boolean;
  envelope: CapabilityTaskStatusEnvelope;
}

export interface CapabilityTaskStatusBridge {
  publishTaskStatus: (
    envelope: CapabilityTaskStatusEnvelope,
  ) => CapabilityTaskStatusReceipt;
}
