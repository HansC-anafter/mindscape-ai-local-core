import { describe, expect, it, vi } from 'vitest';

import {
  CAPABILITY_TASK_STATUS_EVENT,
  type CapabilityTaskStatusEnvelope,
} from './capability-task-status-types';
import { createTaskStatusBridge } from './capability-task-status-bridge';

function baseEnvelope(): CapabilityTaskStatusEnvelope {
  return {
    schemaVersion: 'capability_task_status.v1',
    workspaceId: 'ws_demo',
    capabilityCode: 'demo',
    actionId: 'demo.actions.queue',
    status: 'accepted',
    submissionId: 'req_123',
    statusUrl: '/api/v1/demo/intake/req_123',
    submittedAt: '2026-06-18T00:00:00.000Z',
  };
}

describe('capability task status bridge', () => {
  it('accepts durable submission status before an execution id exists', () => {
    const bridge = createTaskStatusBridge();
    const listener = vi.fn();
    window.addEventListener(CAPABILITY_TASK_STATUS_EVENT, listener);

    try {
      const receipt = bridge.publishTaskStatus(baseEnvelope());

      expect(receipt.emitted).toBe(true);
      expect(receipt.duplicate).toBe(false);
      expect(receipt.envelope.executionId).toBeUndefined();
      expect(receipt.envelope.submissionId).toBe('req_123');
      expect(listener).toHaveBeenCalledTimes(1);
      expect((listener.mock.calls[0][0] as CustomEvent).detail).toMatchObject({
        workspaceId: 'ws_demo',
        capabilityCode: 'demo',
        actionId: 'demo.actions.queue',
        status: 'accepted',
        submissionId: 'req_123',
      });
    } finally {
      window.removeEventListener(CAPABILITY_TASK_STATUS_EVENT, listener);
    }
  });

  it('dedupes repeated identical status events within the ttl', () => {
    const bridge = createTaskStatusBridge();
    const listener = vi.fn();
    window.addEventListener(CAPABILITY_TASK_STATUS_EVENT, listener);

    try {
      const first = bridge.publishTaskStatus(baseEnvelope());
      const second = bridge.publishTaskStatus(baseEnvelope());

      expect(first.emitted).toBe(true);
      expect(second.emitted).toBe(false);
      expect(second.duplicate).toBe(true);
      expect(listener).toHaveBeenCalledTimes(1);
    } finally {
      window.removeEventListener(CAPABILITY_TASK_STATUS_EVENT, listener);
    }
  });

  it('emits a handoff update when execution ids arrive for the same submission', () => {
    const bridge = createTaskStatusBridge();
    const listener = vi.fn();
    window.addEventListener(CAPABILITY_TASK_STATUS_EVENT, listener);

    try {
      const accepted = bridge.publishTaskStatus(baseEnvelope());
      const queued = bridge.publishTaskStatus({
        ...baseEnvelope(),
        status: 'queued',
        executionIds: ['exec_1', 'exec_2'],
        playbookCode: 'demo_playbook',
      });

      expect(accepted.key).toBe(queued.key);
      expect(queued.emitted).toBe(true);
      expect(queued.envelope.executionId).toBe('exec_1');
      expect(queued.envelope.executionIds).toEqual(['exec_1', 'exec_2']);
      expect(listener).toHaveBeenCalledTimes(2);
    } finally {
      window.removeEventListener(CAPABILITY_TASK_STATUS_EVENT, listener);
    }
  });

  it('rejects status events without submission or execution identity', () => {
    const bridge = createTaskStatusBridge();

    expect(() => bridge.publishTaskStatus({
      ...baseEnvelope(),
      submissionId: '',
      executionIds: [],
    })).toThrow('capability_task_status_identity_missing');
  });
});
