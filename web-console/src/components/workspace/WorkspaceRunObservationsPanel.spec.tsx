import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  fetchRunObservationEvents,
  fetchRunObservationsSummary,
} from '@/lib/workspace-runs/run-observations-api';
import WorkspaceRunObservationsPanel from './WorkspaceRunObservationsPanel';

vi.mock('@/lib/workspace-runs/run-observations-api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/workspace-runs/run-observations-api')>();
  return {
    ...actual,
    fetchRunObservationsSummary: vi.fn(),
    fetchRunObservationEvents: vi.fn(),
  };
});

describe('WorkspaceRunObservationsPanel', () => {
  beforeEach(() => {
    vi.mocked(fetchRunObservationsSummary).mockResolvedValue({
      workspace_id: 'ws_test',
      source_kind: 'external_runner',
      external_active_count: 1,
      counts: { running: 1 },
      cards: [
        {
          run_id: 'meeting-pd-ltx-30s-e2e-2026-05-21',
          execution_id: 'meeting-pd-ltx-30s-e2e-2026-05-21',
          workspace_id: 'ws_test',
          provider_code: 'external_runner:comfyui_ltx',
          source_kind: 'external_runner',
          status: 'running',
          display_title: 'Meeting PD LTX 30s Storyboard',
          summary: 'shot03_try_on b19 running',
          payload: {
            stage_code: 'shot03_try_on:b19',
            stage_index: 3,
            stage_total: 6,
            prompt_id: 'prompt-b19',
            elapsed_seconds: 91,
            queue_running: 1,
            queue_pending: 0,
          },
          heartbeat_at: '2026-05-21T10:00:00Z',
          created_at: '2026-05-21T09:00:00Z',
          updated_at: '2026-05-21T10:00:00Z',
        },
      ],
    });
    vi.mocked(fetchRunObservationEvents).mockResolvedValue({
      workspace_id: 'ws_test',
      run_id: 'meeting-pd-ltx-30s-e2e-2026-05-21',
      events: [
        {
          feed_id: 'feed-1',
          workspace_id: 'ws_test',
          run_id: 'meeting-pd-ltx-30s-e2e-2026-05-21',
          status: 'running',
          source_kind: 'external_runner',
          payload: {
            stage_code: 'shot03_try_on:b19',
          },
        },
      ],
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders external runner cards from the workspace-scoped summary', async () => {
    render(<WorkspaceRunObservationsPanel apiUrl="http://api.test" workspaceId="ws_test" />);

    await waitFor(() => {
      expect(screen.getByText('Meeting PD LTX 30s Storyboard')).toBeInTheDocument();
    });
    expect(screen.getByText('shot03_try_on b19 running')).toBeInTheDocument();
    expect(screen.getByText('Stage: shot03_try_on:b19')).toBeInTheDocument();
    expect(screen.getByText('Prompt: prompt-b19')).toBeInTheDocument();
    expect(fetchRunObservationsSummary).toHaveBeenCalledWith({
      apiUrl: 'http://api.test',
      workspaceId: 'ws_test',
      activeOnly: true,
      limit: 20,
    });
    expect(fetchRunObservationEvents).not.toHaveBeenCalled();
  });

  it('fetches selected run detail only after card selection', async () => {
    render(<WorkspaceRunObservationsPanel apiUrl="http://api.test" workspaceId="ws_test" />);

    const card = await screen.findByTestId(
      'run-observation-card-meeting-pd-ltx-30s-e2e-2026-05-21',
    );
    fireEvent.click(card);

    await waitFor(() => {
      expect(fetchRunObservationEvents).toHaveBeenCalledWith({
        apiUrl: 'http://api.test',
        workspaceId: 'ws_test',
        runId: 'meeting-pd-ltx-30s-e2e-2026-05-21',
        limit: 50,
      });
    });
    await waitFor(() => {
      expect(
        screen.getAllByText((_, element) => element?.textContent === 'running · shot03_try_on:b19')
          .length,
      ).toBeGreaterThan(0);
    });
  });

  it('shows operator interruption as stopped instead of failed generation copy', async () => {
    vi.mocked(fetchRunObservationsSummary).mockResolvedValue({
      workspace_id: 'ws_test',
      source_kind: 'external_runner',
      external_active_count: 0,
      counts: { cancelled: 1 },
      cards: [
        {
          run_id: 'cancelled-run',
          execution_id: 'cancelled-run',
          workspace_id: 'ws_test',
          provider_code: 'external_runner:comfyui_ltx',
          source_kind: 'external_runner',
          status: 'cancelled',
          display_title: 'Meeting PD LTX 30s Storyboard',
          summary: 'operator interrupt',
          payload: {
            stage_code: 'shot03_try_on:b19',
            stop_reason: 'operator_interrupt',
          },
        },
      ],
    });

    render(<WorkspaceRunObservationsPanel apiUrl="http://api.test" workspaceId="ws_test" />);

    await waitFor(() => {
      expect(screen.getByText('Stopped by operator')).toBeInTheDocument();
    });
    expect(screen.queryByText(/failed/i)).not.toBeInTheDocument();
  });
});
