import { describe, expect, it } from 'vitest';

import {
  buildExecutionStepMap,
  getFocusedExecutionGroups,
  getTimelineExecutionBuckets,
  upsertExecutionStepMap,
} from './helpers';

describe('timeline helpers', () => {
  it('groups executions into running, pending confirmation, and archived buckets', () => {
    const executions = [
      {
        execution_id: 'pending-confirmation',
        workspace_id: 'workspace-1',
        status: 'running',
        paused_at: '2026-03-24T10:05:00Z',
        current_step_index: 1,
        total_steps: 3,
        created_at: '2026-03-24T10:00:00Z',
      },
      {
        execution_id: 'running',
        workspace_id: 'workspace-1',
        status: 'running',
        started_at: '2026-03-24T10:06:00Z',
        current_step_index: 0,
        total_steps: 2,
        created_at: '2026-03-24T10:01:00Z',
      },
      {
        execution_id: 'archived',
        workspace_id: 'workspace-1',
        status: 'succeeded',
        current_step_index: 1,
        total_steps: 2,
        created_at: '2026-03-24T08:00:00Z',
      },
    ];
    const stepMap = buildExecutionStepMap([
      {
        ...executions[0],
        steps: [
          {
            id: 'step-1',
            execution_id: 'pending-confirmation',
            step_index: 1,
            step_name: 'Review',
            status: 'pending',
            requires_confirmation: true,
            confirmation_status: 'pending',
          },
        ],
      },
    ]);

    const buckets = getTimelineExecutionBuckets(
      executions as any,
      stepMap,
      new Date('2026-03-24T10:30:00Z')
    );

    expect(buckets.pendingConfirmationExecutions.map((execution) => execution.execution_id)).toEqual([
      'pending-confirmation',
    ]);
    expect(buckets.runningExecutions.map((execution) => execution.execution_id)).toEqual([
      'running',
    ]);
    expect(buckets.archivedExecutions.map((execution) => execution.execution_id)).toEqual([
      'archived',
    ]);
  });

  it('groups focused executions by the current playbook', () => {
    const groups = getFocusedExecutionGroups(
      [
        {
          execution_id: 'focus',
          workspace_id: 'workspace-1',
          playbook_code: 'ig',
          status: 'running',
          current_step_index: 0,
          total_steps: 1,
          created_at: '2026-03-24T10:05:00Z',
        },
        {
          execution_id: 'same-playbook',
          workspace_id: 'workspace-1',
          playbook_code: 'ig',
          status: 'failed',
          current_step_index: 0,
          total_steps: 1,
          created_at: '2026-03-24T10:04:00Z',
        },
        {
          execution_id: 'other-playbook',
          workspace_id: 'workspace-1',
          playbook_code: 'research',
          status: 'succeeded',
          current_step_index: 0,
          total_steps: 1,
          created_at: '2026-03-24T10:03:00Z',
        },
      ] as any,
      'focus'
    );

    expect(groups?.currentExecution.execution_id).toBe('focus');
    expect(groups?.samePlaybookExecutions.map((execution) => execution.execution_id)).toEqual([
      'same-playbook',
    ]);
    expect(groups?.otherPlaybookExecutions.map((execution) => execution.execution_id)).toEqual([
      'other-playbook',
    ]);
  });

  it('upserts execution steps without mutating previous state', () => {
    const original = new Map([
      [
        'execution-1',
        [
          {
            id: 'step-1',
            execution_id: 'execution-1',
            step_index: 0,
            step_name: 'Start',
            status: 'running',
            requires_confirmation: false,
          },
        ],
      ],
    ]);

    const updated = upsertExecutionStepMap(original as any, 'execution-1', {
      id: 'step-2',
      execution_id: 'execution-1',
      step_index: 1,
      step_name: 'Review',
      status: 'pending',
      requires_confirmation: true,
    } as any);

    expect(original.get('execution-1')).toHaveLength(1);
    expect(updated.get('execution-1')).toHaveLength(2);
    expect(updated.get('execution-1')?.[1].id).toBe('step-2');
  });
});
