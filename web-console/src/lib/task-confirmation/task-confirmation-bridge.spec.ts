import { describe, expect, it, vi } from 'vitest';

import {
  CAPABILITY_TASK_CONFIRMATION_EVENT,
  CAPABILITY_TASK_CONFIRMATION_EXECUTION_EVENT,
  CAPABILITY_TASK_CONFIRMATION_LEGACY_EVENT,
} from '@/types/capability-workbench';
import { createTaskConfirmationBridge } from './task-confirmation-bridge';

function baseEnvelope() {
  return {
    schemaVersion: 'capability_task_confirmation.v1' as const,
    workspaceId: 'ws_demo',
    executionId: 'exec_demo',
    playbookCode: 'ig_batch_pin_references',
    status: 'queued' as const,
    submittedAt: '2026-06-18T00:00:00.000Z',
    inputs: { workspace_id: 'ws_demo' },
  };
}

describe('task confirmation bridge', () => {
  it('emits canonical, legacy, and execution events for a new confirmation', () => {
    const bridge = createTaskConfirmationBridge();
    const canonicalListener = vi.fn();
    const legacyListener = vi.fn();
    const executionListener = vi.fn();
    window.addEventListener(CAPABILITY_TASK_CONFIRMATION_EVENT, canonicalListener);
    window.addEventListener(CAPABILITY_TASK_CONFIRMATION_LEGACY_EVENT, legacyListener);
    window.addEventListener(CAPABILITY_TASK_CONFIRMATION_EXECUTION_EVENT, executionListener);

    try {
      const receipt = bridge.confirmTaskSubmission(baseEnvelope());

      expect(receipt.emitted).toBe(true);
      expect(receipt.duplicate).toBe(false);
      expect(canonicalListener).toHaveBeenCalledTimes(1);
      expect(legacyListener).toHaveBeenCalledTimes(1);
      expect(executionListener).toHaveBeenCalledTimes(1);
      expect((canonicalListener.mock.calls[0][0] as CustomEvent).detail).toMatchObject({
        workspaceId: 'ws_demo',
        executionId: 'exec_demo',
        playbookCode: 'ig_batch_pin_references',
      });
      expect((legacyListener.mock.calls[0][0] as CustomEvent).detail).toMatchObject({
        workspaceId: 'ws_demo',
        executionId: 'exec_demo',
        playbookCode: 'ig_batch_pin_references',
      });
      expect((executionListener.mock.calls[0][0] as CustomEvent).detail).toMatchObject({
        type: 'execution_started',
        data: {
          executionId: 'exec_demo',
          playbookCode: 'ig_batch_pin_references',
        },
      });
    } finally {
      window.removeEventListener(CAPABILITY_TASK_CONFIRMATION_EVENT, canonicalListener);
      window.removeEventListener(CAPABILITY_TASK_CONFIRMATION_LEGACY_EVENT, legacyListener);
      window.removeEventListener(CAPABILITY_TASK_CONFIRMATION_EXECUTION_EVENT, executionListener);
    }
  });

  it('dedupes repeated confirmations by workspace, execution, and playbook', () => {
    const bridge = createTaskConfirmationBridge();
    const listener = vi.fn();
    window.addEventListener(CAPABILITY_TASK_CONFIRMATION_EVENT, listener);

    try {
      const first = bridge.confirmTaskSubmission(baseEnvelope());
      const second = bridge.confirmTaskSubmission({
        ...baseEnvelope(),
        status: 'running',
      });

      expect(first.emitted).toBe(true);
      expect(second.emitted).toBe(false);
      expect(second.duplicate).toBe(true);
      expect(second.envelope.status).toBe('running');
      expect(listener).toHaveBeenCalledTimes(1);
    } finally {
      window.removeEventListener(CAPABILITY_TASK_CONFIRMATION_EVENT, listener);
    }
  });

  it('rejects confirmations without required identity fields', () => {
    const bridge = createTaskConfirmationBridge();

    expect(() => bridge.confirmTaskSubmission({
      ...baseEnvelope(),
      executionId: '',
    })).toThrow('task_confirmation_required_fields_missing');
  });
});
