import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { useRunObservationsSummary } from '@/lib/workspace-runs/useRunObservationsSummary';
import WorkspacePausedRunsPanel from './WorkspacePausedRunsPanel';

vi.mock('@/contexts/WorkspaceDataContext', () => ({
  useWorkspaceDataOptional: vi.fn(),
}));

vi.mock('@/lib/workspace-runs/useRunObservationsSummary', () => ({
  useRunObservationsSummary: vi.fn(),
}));

describe('WorkspacePausedRunsPanel', () => {
  beforeEach(() => {
    vi.mocked(useWorkspaceDataOptional).mockReturnValue({
      executions: [
        {
          execution_id: 'exec_ig_paused',
          status: 'paused',
          playbook_code: 'ig_analyze_following',
          paused_at: '2026-05-22T00:20:00+08:00',
          current_step_index: 2,
          total_steps: 5,
        },
        {
          execution_id: 'exec_running',
          status: 'running',
          playbook_code: 'ig_analyze_following',
        },
      ],
    } as any);
    vi.mocked(useRunObservationsSummary).mockReturnValue({
      summary: {
        workspace_id: 'ws_test',
        source_kind: 'external_runner',
        external_active_count: 1,
        counts: { paused: 1 },
        cards: [
          {
            run_id: 'comfyui-paused-run',
            execution_id: 'comfyui-paused-run',
            workspace_id: 'ws_test',
            provider_code: 'external_runner:comfyui_ltx',
            source_kind: 'external_runner',
            status: 'paused',
            display_title: 'Meeting PD LTX 30s Storyboard',
            summary: 'shot03 paused',
            payload: {
              stage_code: 'shot03_try_on:b19',
              prompt_id: 'prompt-b19',
              stop_reason: 'operator_pause',
            },
          },
          {
            run_id: 'comfyui-running-run',
            workspace_id: 'ws_test',
            provider_code: 'external_runner:comfyui_ltx',
            source_kind: 'external_runner',
            status: 'running',
          },
        ],
      },
      isLoading: false,
      error: null,
      externalActiveCount: 1,
    });
  });

  it('combines workspace paused executions and external runner paused observations', () => {
    render(<WorkspacePausedRunsPanel apiUrl="http://api.test" workspaceId="ws_test" />);

    expect(screen.getByText('Workspace Paused Runs')).toBeInTheDocument();
    expect(screen.getByText('External Runners')).toBeInTheDocument();
    expect(screen.getByText('Workspace Executions')).toBeInTheDocument();
    expect(screen.getByText('Meeting PD LTX 30s Storyboard')).toBeInTheDocument();
    expect(screen.getByText('Stage: shot03_try_on:b19')).toBeInTheDocument();
    expect(screen.getByText('Paused by operator')).toBeInTheDocument();
    expect(screen.getByText('ig_analyze_following')).toBeInTheDocument();
    expect(screen.queryByText('comfyui-running-run')).not.toBeInTheDocument();
  });

  it('shows an empty state when no paused workspace run exists', () => {
    vi.mocked(useWorkspaceDataOptional).mockReturnValue({ executions: [] } as any);
    vi.mocked(useRunObservationsSummary).mockReturnValue({
      summary: {
        workspace_id: 'ws_test',
        source_kind: 'external_runner',
        external_active_count: 0,
        counts: {},
        cards: [],
      },
      isLoading: false,
      error: null,
      externalActiveCount: 0,
    });

    render(<WorkspacePausedRunsPanel apiUrl="http://api.test" workspaceId="ws_test" />);

    expect(screen.getByText('No paused workspace runs.')).toBeInTheDocument();
  });
});
