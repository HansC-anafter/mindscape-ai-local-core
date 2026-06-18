import type { ReactNode } from 'react';

export {
  CAPABILITY_TASK_STATUS_EVENT,
} from '../lib/capability-task-status/capability-task-status-types';
export type {
  CapabilityTaskStatusBridge,
  CapabilityTaskStatusEnvelope,
  CapabilityTaskStatusReceipt,
  CapabilityTaskStatusTarget,
  CapabilityTaskStatusValue,
} from '../lib/capability-task-status/capability-task-status-types';

export const CAPABILITY_TASK_CONFIRMATION_EVENT = 'mindscape:task_confirmation' as const;
export const CAPABILITY_TASK_CONFIRMATION_LEGACY_EVENT = 'mindscape:execution_started' as const;
export const CAPABILITY_TASK_CONFIRMATION_EXECUTION_EVENT = 'execution-event' as const;

export type CapabilityTaskConfirmationStatus =
  | 'submitted'
  | 'queued'
  | 'running'
  | 'existing'
  | 'satisfied'
  | 'confirmed';

export interface CapabilityTaskConfirmationEnvelope {
  schemaVersion: 'capability_task_confirmation.v1';
  workspaceId: string;
  executionId: string;
  playbookCode: string;
  taskType?: string;
  status: CapabilityTaskConfirmationStatus;
  submittedAt?: string;
  confirmedAt?: string;
  targetKey?: string;
  targetKind?: string;
  displayLabel?: string;
  source?: string;
  inputs?: Record<string, unknown>;
  ttlMs?: number;
}

export interface CapabilityTaskConfirmationReceipt {
  key: string;
  emitted: boolean;
  duplicate: boolean;
  envelope: CapabilityTaskConfirmationEnvelope;
}

export interface CapabilityTaskConfirmationBridge {
  confirmTaskSubmission: (
    envelope: CapabilityTaskConfirmationEnvelope,
  ) => CapabilityTaskConfirmationReceipt;
  publishTaskStatus?: (
    envelope: import('../lib/capability-task-status/capability-task-status-types').CapabilityTaskStatusEnvelope,
  ) => import('../lib/capability-task-status/capability-task-status-types').CapabilityTaskStatusReceipt;
}

export type CapabilityWorkbenchStatusTone =
  | 'neutral'
  | 'active'
  | 'warning'
  | 'danger'
  | 'success';

export type CapabilityWorkbenchPrimaryObjectKind =
  | 'storyboard'
  | 'render_batch'
  | 'reference_collection'
  | 'artifact'
  | 'run'
  | 'custom';

export type CapabilityWorkbenchSessionStatus =
  | 'idle'
  | 'active'
  | 'paused'
  | 'failed'
  | 'completed';

export interface CapabilityWorkbenchInfoReference {
  key: string;
  label: string;
  value: string;
  copyValue: string;
}

export interface CapabilityWorkbenchInfoStatus {
  key: string;
  label: string;
  value: string;
  tone: CapabilityWorkbenchStatusTone;
}

export interface CapabilityWorkbenchInfoMetadata {
  schemaVersion: 'capability_workbench_info_metadata.v1';
  capability: {
    code: string;
    label: string;
  };
  workspace: {
    id: string;
    label?: string;
  };
  primaryObject: {
    kind: CapabilityWorkbenchPrimaryObjectKind;
    id: string;
    label?: string;
    ownerCapability?: string;
  };
  session?: {
    id: string;
    kind: string;
    status?: CapabilityWorkbenchSessionStatus;
  };
  artifact?: {
    id: string;
    kind: string;
    label?: string;
  };
  selection?: {
    sceneId?: string;
    shotId?: string;
    mode?: string;
    department?: string;
  };
  references: CapabilityWorkbenchInfoReference[];
  status: CapabilityWorkbenchInfoStatus[];
}

export interface CapabilityWorkbenchCommandHeaderProps {
  brandSlot: ReactNode;
  modeSlot?: ReactNode;
  primaryToolbarSlot?: ReactNode;
  contextToolbarSlot?: ReactNode;
  statusSlot?: ReactNode;
  utilitySlot?: ReactNode;
  mobileVariant?: 'default' | 'compact';
  mobileCollapsible?: boolean;
  mobileDefaultCollapsed?: boolean;
  className?: string;
}

const PRIMARY_OBJECT_KINDS = new Set<string>([
  'storyboard',
  'render_batch',
  'reference_collection',
  'artifact',
  'run',
  'custom',
]);

const SESSION_STATUSES = new Set<string>([
  'idle',
  'active',
  'paused',
  'failed',
  'completed',
]);

const STATUS_TONES = new Set<string>([
  'neutral',
  'active',
  'warning',
  'danger',
  'success',
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === 'string';
}

function isOptionalString(value: unknown): value is string | undefined {
  return value === undefined || isString(value);
}

function isReference(value: unknown): value is CapabilityWorkbenchInfoReference {
  return (
    isRecord(value) &&
    isString(value.key) &&
    isString(value.label) &&
    isString(value.value) &&
    isString(value.copyValue)
  );
}

function isStatus(value: unknown): value is CapabilityWorkbenchInfoStatus {
  return (
    isRecord(value) &&
    isString(value.key) &&
    isString(value.label) &&
    isString(value.value) &&
    isString(value.tone) &&
    STATUS_TONES.has(value.tone)
  );
}

export function isCapabilityWorkbenchInfoMetadata(
  value: unknown,
): value is CapabilityWorkbenchInfoMetadata {
  if (!isRecord(value)) {
    return false;
  }

  if (value.schemaVersion !== 'capability_workbench_info_metadata.v1') {
    return false;
  }

  if (!isRecord(value.capability) || !isString(value.capability.code) || !isString(value.capability.label)) {
    return false;
  }

  if (!isRecord(value.workspace) || !isString(value.workspace.id) || !isOptionalString(value.workspace.label)) {
    return false;
  }

  if (
    !isRecord(value.primaryObject) ||
    !isString(value.primaryObject.kind) ||
    !PRIMARY_OBJECT_KINDS.has(value.primaryObject.kind) ||
    !isString(value.primaryObject.id) ||
    !isOptionalString(value.primaryObject.label) ||
    !isOptionalString(value.primaryObject.ownerCapability)
  ) {
    return false;
  }

  if (value.session !== undefined) {
    if (
      !isRecord(value.session) ||
      !isString(value.session.id) ||
      !isString(value.session.kind) ||
      (
        value.session.status !== undefined &&
        (!isString(value.session.status) || !SESSION_STATUSES.has(value.session.status))
      )
    ) {
      return false;
    }
  }

  if (value.artifact !== undefined) {
    if (
      !isRecord(value.artifact) ||
      !isString(value.artifact.id) ||
      !isString(value.artifact.kind) ||
      !isOptionalString(value.artifact.label)
    ) {
      return false;
    }
  }

  if (value.selection !== undefined) {
    if (
      !isRecord(value.selection) ||
      !isOptionalString(value.selection.sceneId) ||
      !isOptionalString(value.selection.shotId) ||
      !isOptionalString(value.selection.mode) ||
      !isOptionalString(value.selection.department)
    ) {
      return false;
    }
  }

  return (
    Array.isArray(value.references) &&
    value.references.every(isReference) &&
    Array.isArray(value.status) &&
    value.status.every(isStatus)
  );
}

export function assertCapabilityWorkbenchInfoMetadata(
  value: unknown,
): CapabilityWorkbenchInfoMetadata {
  if (!isCapabilityWorkbenchInfoMetadata(value)) {
    throw new Error('Invalid capability workbench info metadata contract');
  }
  return value;
}
