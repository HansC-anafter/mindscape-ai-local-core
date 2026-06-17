import {
  CAPABILITY_TASK_CONFIRMATION_EVENT,
  CAPABILITY_TASK_CONFIRMATION_EXECUTION_EVENT,
  CAPABILITY_TASK_CONFIRMATION_LEGACY_EVENT,
  type CapabilityTaskConfirmationBridge,
  type CapabilityTaskConfirmationEnvelope,
  type CapabilityTaskConfirmationReceipt,
} from '@/types/capability-workbench';

const DEFAULT_CONFIRMATION_TTL_MS = 30_000;

interface ConfirmationRecord {
  envelope: CapabilityTaskConfirmationEnvelope;
  recordedAt: number;
}

declare global {
  interface Window {
    __MindscapeTaskConfirmationBridge?: CapabilityTaskConfirmationBridge | null;
  }
}

function readText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function normalizeEnvelope(
  envelope: CapabilityTaskConfirmationEnvelope,
): CapabilityTaskConfirmationEnvelope {
  const workspaceId = readText(envelope.workspaceId);
  const executionId = readText(envelope.executionId);
  const playbookCode = readText(envelope.playbookCode);
  if (!workspaceId || !executionId || !playbookCode) {
    throw new Error('task_confirmation_required_fields_missing');
  }
  const nowIso = new Date().toISOString();
  return {
    ...envelope,
    schemaVersion: 'capability_task_confirmation.v1',
    workspaceId,
    executionId,
    playbookCode,
    status: envelope.status || 'queued',
    confirmedAt: envelope.confirmedAt || nowIso,
    submittedAt: envelope.submittedAt || envelope.confirmedAt || nowIso,
    inputs: envelope.inputs || {},
    ttlMs: typeof envelope.ttlMs === 'number' && envelope.ttlMs > 0
      ? envelope.ttlMs
      : DEFAULT_CONFIRMATION_TTL_MS,
  };
}

function buildConfirmationKey(envelope: CapabilityTaskConfirmationEnvelope): string {
  return `${envelope.workspaceId}:${envelope.executionId}:${envelope.playbookCode}`;
}

function dispatchWindowEvent(eventName: string, detail: unknown): void {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(new CustomEvent(eventName, { detail }));
}

function emitConfirmationEvents(envelope: CapabilityTaskConfirmationEnvelope): void {
  dispatchWindowEvent(CAPABILITY_TASK_CONFIRMATION_EVENT, envelope);
  dispatchWindowEvent(CAPABILITY_TASK_CONFIRMATION_LEGACY_EVENT, {
    workspaceId: envelope.workspaceId,
    executionId: envelope.executionId,
    playbookCode: envelope.playbookCode,
    startedAt: envelope.submittedAt,
    inputs: envelope.inputs || {},
  });
  dispatchWindowEvent(CAPABILITY_TASK_CONFIRMATION_EXECUTION_EVENT, {
    type: 'execution_started',
    data: {
      executionId: envelope.executionId,
      playbookCode: envelope.playbookCode,
      playbookName: envelope.displayLabel || envelope.playbookCode,
      runNumber: 0,
    },
  });
}

export function createTaskConfirmationBridge(): CapabilityTaskConfirmationBridge {
  const confirmations = new Map<string, ConfirmationRecord>();

  return {
    confirmTaskSubmission(envelope): CapabilityTaskConfirmationReceipt {
      const normalizedEnvelope = normalizeEnvelope(envelope);
      const key = buildConfirmationKey(normalizedEnvelope);
      const now = Date.now();
      const previous = confirmations.get(key);
      const ttlMs = normalizedEnvelope.ttlMs || DEFAULT_CONFIRMATION_TTL_MS;
      const duplicate = Boolean(previous && now - previous.recordedAt <= ttlMs);
      confirmations.set(key, {
        envelope: normalizedEnvelope,
        recordedAt: now,
      });
      if (!duplicate) {
        emitConfirmationEvents(normalizedEnvelope);
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

let browserBridge: CapabilityTaskConfirmationBridge | null = null;

export function getTaskConfirmationBridge(): CapabilityTaskConfirmationBridge {
  if (!browserBridge) {
    browserBridge = createTaskConfirmationBridge();
  }
  if (typeof window !== 'undefined') {
    window.__MindscapeTaskConfirmationBridge = browserBridge;
  }
  return browserBridge;
}
