import { describe, expect, it } from 'vitest';

import {
  getTaskDisplayTitle,
  getVisibleBackgroundTasks,
  splitPendingTaskCollections,
} from './helpers';

describe('pendingTasks helpers', () => {
  it('splits background tasks and decision tasks consistently', () => {
    const result = splitPendingTaskCollections(
      [
        {
          id: 'background-pending',
          workspace_id: 'workspace-1',
          pack_id: 'habit_learning',
          status: 'PENDING',
          created_at: '2026-03-24T10:00:00Z',
        },
        {
          id: 'auto-intent',
          workspace_id: 'workspace-1',
          task_type: 'auto_intent_extraction',
          status: 'PENDING',
          created_at: '2026-03-24T10:00:00Z',
        },
        {
          id: 'system-task',
          workspace_id: 'workspace-1',
          pack_id: 'execution_status_query',
          status: 'PENDING',
          created_at: '2026-03-24T10:00:00Z',
        },
        {
          id: 'foreground-pending',
          workspace_id: 'workspace-1',
          pack_id: 'ig',
          status: 'PENDING',
          created_at: '2026-03-24T10:00:00Z',
        },
        {
          id: 'recent-success',
          workspace_id: 'workspace-1',
          pack_id: 'ig',
          status: 'SUCCEEDED',
          created_at: '2026-03-24T10:00:00Z',
          completed_at: '2026-03-24T10:04:30Z',
        },
        {
          id: 'stale-success',
          workspace_id: 'workspace-1',
          pack_id: 'ig',
          status: 'SUCCEEDED',
          created_at: '2026-03-24T09:30:00Z',
          completed_at: '2026-03-24T09:40:00Z',
        },
      ],
      new Date('2026-03-24T10:05:00Z').getTime()
    );

    expect(result.backgroundTasks.map((task) => task.id)).toEqual(['background-pending']);
    expect(result.displayTasks.map((task) => task.id)).toEqual([
      'foreground-pending',
      'recent-success',
    ]);
  });

  it('hides background tasks that already have an enabled routine', () => {
    const visibleTasks = getVisibleBackgroundTasks(
      [
        {
          id: 'habit-1',
          workspace_id: 'workspace-1',
          pack_id: 'habit_learning',
          status: 'PENDING',
          created_at: '2026-03-24T10:00:00Z',
        },
        {
          id: 'habit-2',
          workspace_id: 'workspace-1',
          pack_id: 'trend_monitoring',
          status: 'PENDING',
          created_at: '2026-03-24T10:00:00Z',
          result: { llm_analysis: { is_background: true } },
        },
      ],
      [{ playbook_code: 'habit_learning', enabled: true }]
    );

    expect(visibleTasks.map((task) => task.id)).toEqual(['habit-2']);
  });

  it('prefers explicit task text before fallback playbook codes', () => {
    expect(
      getTaskDisplayTitle({
        id: 'task-with-title',
        workspace_id: 'workspace-1',
        title: 'Review references',
        status: 'PENDING',
        created_at: '2026-03-24T10:00:00Z',
      })
    ).toBe('Review references');

    expect(
      getTaskDisplayTitle({
        id: 'task-with-summary',
        workspace_id: 'workspace-1',
        summary: 'Create report',
        status: 'PENDING',
        created_at: '2026-03-24T10:00:00Z',
      })
    ).toBe('Create report');

    expect(
      getTaskDisplayTitle({
        id: 'task-with-code',
        workspace_id: 'workspace-1',
        pack_id: 'unknown-pack',
        status: 'PENDING',
        created_at: '2026-03-24T10:00:00Z',
      })
    ).toBe('unknown-pack');
  });
});
