import { afterEach, describe, expect, it, vi } from 'vitest';

import { loadExecutionSidebarData } from './executionSidebarData';

function jsonResponse(data: unknown, ok = true) {
  return Promise.resolve({
    ok,
    json: () => Promise.resolve(data),
  } as Response);
}

describe('execution sidebar data seam', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('loads project metadata and execution tree without changing endpoint shapes', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith('/projects/project_1')) {
        return jsonResponse({ name: 'Launch Project' });
      }
      if (url.endsWith('/projects/project_1/execution-tree')) {
        return jsonResponse({
          playbookGroups: [
            {
              playbookCode: 'site_spec_generation',
              playbookName: 'Site Spec',
              stats: { running: 1, paused: 0, queued: 1, completed: 0, failed: 0 },
              executions: [
                {
                  execution_id: 'exec_late',
                  status: 'running',
                  started_at: '2026-06-21T02:00:00Z',
                  current_step_index: 1,
                  current_step_name: 'Build',
                  total_steps: 3,
                  playbook_code: 'site_spec_generation',
                  playbook_title: 'Site Spec',
                },
                {
                  execution_id: 'exec_early',
                  status: 'queued',
                  started_at: '2026-06-21T01:00:00Z',
                  total_steps: 2,
                  playbook_code: 'site_spec_generation',
                },
              ],
            },
          ],
        });
      }
      return jsonResponse({}, false);
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await loadExecutionSidebarData({
      apiUrl: 'http://api.test',
      projectId: 'project_1',
      workspaceId: 'ws_1',
    });

    expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/v1/workspaces/ws_1/projects/project_1');
    expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/v1/workspaces/ws_1/projects/project_1/execution-tree');
    expect(result.projectName).toBe('Launch Project');
    expect(result.playbookGroups?.[0]?.executions.map((execution) => execution.executionId)).toEqual([
      'exec_early',
      'exec_late',
    ]);
    expect(result.playbookGroups?.[0]?.executions.map((execution) => execution.runNumber)).toEqual([1, 2]);
  });

  it('loads workspace execution tasks and accumulates group stats', async () => {
    const fetchMock = vi.fn(() => jsonResponse({
      tasks: [
        {
          execution_id: 'exec_running',
          status: 'running',
          started_at: '2026-06-21T02:00:00Z',
          current_step_index: 0,
          current_step_name: 'Start',
          playbook_code: 'build_pack',
          playbook_title: 'Build Pack',
          total_steps: 4,
        },
        {
          execution_id: 'exec_failed',
          status: 'failed',
          started_at: '2026-06-21T01:00:00Z',
          playbook_code: 'build_pack',
          playbook_title: 'Build Pack',
        },
      ],
    }));
    vi.stubGlobal('fetch', fetchMock);

    const result = await loadExecutionSidebarData({
      apiUrl: 'http://api.test',
      projectId: '',
      workspaceId: 'ws_1',
    });

    expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/v1/workspaces/ws_1/tasks?limit=50&task_type=execution&include_completed=true');
    expect(result.projectName).toBe('All Executions');
    expect(result.playbookGroups).toHaveLength(1);
    expect(result.playbookGroups?.[0]?.stats).toMatchObject({ running: 1, failed: 1 });
    expect(result.playbookGroups?.[0]?.executions.map((execution) => execution.executionId)).toEqual([
      'exec_failed',
      'exec_running',
    ]);
  });
});
