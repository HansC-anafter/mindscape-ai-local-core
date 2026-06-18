import {
  CAPABILITY_TASK_STATUS_EVENT,
  type CapabilityTaskStatusBridge,
  type CapabilityTaskStatusEnvelope,
  type CapabilityTaskStatusReceipt,
  type CapabilityTaskStatusValue,
} from './capability-task-status-types';

const DEFAULT_STATUS_TTL_MS = 120_000;

const KNOWN_STATUSES = new Set<CapabilityTaskStatusValue>([
  'submitted',
  'accepted',
  'queued',
  'running',
  'existing',
  'satisfied',
  'confirmed',
  'succeeded',
  'failed',
  'operator_review',
]);

interface StatusRecord {
  envelope: CapabilityTaskStatusEnvelope;
  recordedAt: number;
}

declare global {
  interface Window {
    __MindscapeTaskStatusBridge?: CapabilityTaskStatusBridge | null;
  }
}

function readText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function normalizeStatus(value: unknown): CapabilityTaskStatusValue {
  const normalized = readText(value).toLowerCase();
  return KNOWN_STATUSES.has(normalized as CapabilityTaskStatusValue)
    ? normalized as CapabilityTaskStatusValue
    : 'queued';
}

function normalizeExecutionIds(envelope: CapabilityTaskStatusEnvelope): string[] {
  const executionIds = new Set<string>();
  const executionId = readText(envelope.executionId);
  if (executionId) {
    executionIds.add(executionId);
  }
  (envelope.executionIds || []).forEach((value) => {
    const normalized = readText(value);
    if (normalized) {
      executionIds.add(normalized);
    }
  });
  return Array.from(executionIds);
}

export function normalizeTaskStatusEnvelope(
  envelope: CapabilityTaskStatusEnvelope,
): CapabilityTaskStatusEnvelope {
  const workspaceId = readText(envelope.workspaceId);
  const capabilityCode = readText(envelope.capabilityCode);
  const actionId = readText(envelope.actionId);
  if (!workspaceId || !capabilityCode || !actionId) {
    throw new Error('capability_task_status_required_fields_missing');
  }

  const submissionId = readText(envelope.submissionId);
  const executionIds = normalizeExecutionIds(envelope);
  const executionId = executionIds[0] || '';
  if (!submissionId && !executionId) {
    throw new Error('capability_task_status_identity_missing');
  }

  const nowIso = new Date().toISOString();
  return {
    ...envelope,
    schemaVersion: 'capability_task_status.v1',
    workspaceId,
    capabilityCode,
    actionId,
    status: normalizeStatus(envelope.status),
    submissionId: submissionId || undefined,
    statusUrl: readText(envelope.statusUrl) || undefined,
    executionId: executionId || undefined,
    executionIds,
    playbookCode: readText(envelope.playbookCode) || undefined,
    submittedAt: envelope.submittedAt || nowIso,
    updatedAt: envelope.updatedAt || nowIso,
    source: readText(envelope.source) || undefined,
    ttlMs: typeof envelope.ttlMs === 'number' && envelope.ttlMs > 0
      ? envelope.ttlMs
      : DEFAULT_STATUS_TTL_MS,
  };
}

export function buildTaskStatusKey(envelope: CapabilityTaskStatusEnvelope): string {
  const identity = envelope.submissionId || envelope.executionId || '';
  return `${envelope.workspaceId}:${envelope.capabilityCode}:${envelope.actionId}:${identity}`;
}

function dispatchTaskStatusEvent(envelope: CapabilityTaskStatusEnvelope): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(new CustomEvent(CAPABILITY_TASK_STATUS_EVENT, { detail: envelope }));
}

function statusRecordsMatch(
  previous: CapabilityTaskStatusEnvelope,
  next: CapabilityTaskStatusEnvelope,
): boolean {
  return (
    previous.status === next.status &&
    previous.statusUrl === next.statusUrl &&
    previous.executionId === next.executionId &&
    previous.playbookCode === next.playbookCode &&
    (previous.executionIds || []).join('\n') === (next.executionIds || []).join('\n')
  );
}

function pruneExpired(records: Map<string, StatusRecord>, now: number): void {
  records.forEach((record, key) => {
    const ttlMs = record.envelope.ttlMs || DEFAULT_STATUS_TTL_MS;
    if (now - record.recordedAt > ttlMs) {
      records.delete(key);
    }
  });
}

export function createTaskStatusBridge(): CapabilityTaskStatusBridge {
  const records = new Map<string, StatusRecord>();

  return {
    publishTaskStatus(envelope): CapabilityTaskStatusReceipt {
      const normalizedEnvelope = normalizeTaskStatusEnvelope(envelope);
      const key = buildTaskStatusKey(normalizedEnvelope);
      const now = Date.now();
      pruneExpired(records, now);
      const previous = records.get(key);
      const ttlMs = normalizedEnvelope.ttlMs || DEFAULT_STATUS_TTL_MS;
      const duplicate = Boolean(
        previous &&
        now - previous.recordedAt <= ttlMs &&
        statusRecordsMatch(previous.envelope, normalizedEnvelope),
      );
      records.set(key, {
        envelope: normalizedEnvelope,
        recordedAt: now,
      });
      if (!duplicate) {
        dispatchTaskStatusEvent(normalizedEnvelope);
      }
      return {
        key,
        emitted: !duplicate,
        duplicate,
        envelope: normalizedEnvelope,
      };
    },
  };
}

let browserBridge: CapabilityTaskStatusBridge | null = null;

export function getTaskStatusBridge(): CapabilityTaskStatusBridge {
  if (!browserBridge) {
    browserBridge = createTaskStatusBridge();
  }
  if (typeof window !== 'undefined') {
    window.__MindscapeTaskStatusBridge = browserBridge;
  }
  return browserBridge;
}
