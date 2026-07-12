import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import {
  loadCapabilityUIComponent,
  primeCapabilityUIComponentMetadata,
} from '@/lib/capability-ui-loader';
import { sharedGetFetch } from '@/lib/resilient-fetch';
import { getWorkspaceToolDefinitions } from './useWorkspaceToolDefinitions';
import WorkspaceRunsPanel from './WorkspaceRunsPanel';

vi.mock('@/lib/api-url', () => ({
  getApiBaseUrl: () => 'http://api.test',
}));

vi.mock('@/lib/page-visibility', () => ({
  isDocumentHidden: () => false,
}));

vi.mock('@/contexts/WorkspaceDataContext', () => ({
  useWorkspaceDataOptional: vi.fn(),
}));

vi.mock('@/lib/resilient-fetch', () => ({
  sharedGetFetch: vi.fn(),
}));

vi.mock('@/lib/capability-ui-loader', () => ({
  loadCapabilityUIComponent: vi.fn(),
  primeCapabilityUIComponentMetadata: vi.fn(),
}));

vi.mock('./useWorkspaceToolDefinitions', () => ({
  getWorkspaceToolDefinitions: vi.fn(),
}));

vi.mock('@/components/workspace/WorkspaceRunObservationsPanel', () => ({
  default: () => <div data-testid="workspace-run-observations-panel" />,
}));

vi.mock('@/components/workspace/WorkspacePausedRunsPanel', () => ({
  default: () => <div data-testid="workspace-paused-runs-panel" />,
}));

function jsonResponse(payload: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => payload,
  } as Response;
}

const IG_RUNS_TOOL = {
  tool_key: 'ig:runs_panel',
  id: 'runs_panel',
  capability_code: 'ig',
  capability_label: 'Instagram',
  group: 'capability',
  label: 'Runs',
  slot: 'workspace.right_rail.tool',
  panel_component_code: 'IGRunsWorkspaceToolPanel',
  panel_component: {
    code: 'IGRunsWorkspaceToolPanel',
    path: 'ui/IGRunsWorkspaceToolPanel.tsx',
    description: 'IG runs panel',
    export: 'default',
    artifact_types: [],
    playbook_codes: [],
    import_path: '@/app/capabilities/ig/components/IGRunsWorkspaceToolPanel',
    asset_url: '/api/v1/capability-packs/installed-capabilities/ig/ui-assets/1.0.98/components/IGRunsWorkspaceToolPanel.mjs',
    integrity: 'sha256-test',
    runtime: 'mindscape-react-bridge-v1',
  },
};

describe('WorkspaceRunsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useWorkspaceDataOptional).mockReturnValue({
      executions: [],
      refreshExecutions: vi.fn(),
    } as any);
    vi.mocked(getWorkspaceToolDefinitions).mockResolvedValue([]);
    vi.mocked(loadCapabilityUIComponent).mockResolvedValue(null);
    vi.mocked(primeCapabilityUIComponentMetadata).mockImplementation(() => undefined);
    vi.mocked(sharedGetFetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes('status=running')) {
        return jsonResponse({
          executions: [
            {
              id: 'exec_pin_ref',
              execution_id: 'exec_pin_ref',
              status: 'running',
              playbook_code: 'ig_analyze_pinned_reference',
              params: {
                trigger: 'pin_reference',
                reference_id: 'ref_52c583dbe9834fe790237f841b4a5840',
                source_handle: 'urwoniewon',
              },
              runner_id: 'runner_8374caca',
              heartbeat_at: '2026-06-05T11:13:45.272608+00:00',
              started_at: '2026-06-05T11:07:28.703646+00:00',
            },
            {
              id: 'exec_following',
              execution_id: 'exec_following',
              status: 'running',
              playbook_code: 'ig_analyze_following',
              params: {
                target_username: 'ninaxxya',
                user_data_dir: '/app/data/ig-browser-profiles/chaos.300_',
              },
              runner_id: 'runner_618d42d1',
              heartbeat_at: '2026-06-05T11:13:41.060847+00:00',
              started_at: '2026-06-05T10:49:45.128609+00:00',
            },
          ],
        });
      }
      if (url.includes('status=queued') || url.includes('status=pending')) {
        return jsonResponse({
          executions: [
            {
              id: 'exec_pending',
              execution_id: 'exec_pending',
              status: 'pending',
              playbook_code: 'ig_batch_pin_references',
              params: {
                trigger: 'after_visit',
                source_handle: 'ninaxxya',
                target_handle: 'mamiqqq',
              },
              queue_shard: 'default_local',
              created_at: '2026-06-05T11:09:45.798529+00:00',
            },
          ],
        });
      }
      return jsonResponse({ executions: [] });
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders DB-backed execution debug cards when observations are empty and the capability runs panel is unavailable', async () => {
    render(
      <WorkspaceRunsPanel
        workspaceId="ws_test"
        activeCapabilityCode="ig"
        runObservationsSummary={{
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
        }}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('2 running · 1 pending')).toBeInTheDocument();
    });

    expect(screen.getByText('ig_analyze_pinned_reference')).toBeInTheDocument();
    expect(screen.getByText('ig_analyze_following')).toBeInTheDocument();
    expect(screen.getByText('ig_batch_pin_references')).toBeInTheDocument();
    expect(screen.getByText('urwoniewon')).toBeInTheDocument();
    expect(screen.getByText('ref_52c583dbe9834fe790237f841b4a5840')).toBeInTheDocument();
    expect(screen.getAllByText('ninaxxya').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('mamiqqq')).toBeInTheDocument();
    expect(vi.mocked(sharedGetFetch)).toHaveBeenCalledWith(
      expect.stringContaining('status=running'),
      expect.any(Object),
      expect.objectContaining({ dedupKey: 'workspace-runs-fallback:active:ws_test' }),
    );
    expect(vi.mocked(sharedGetFetch)).toHaveBeenCalledWith(
      expect.stringContaining('status=queued'),
      expect.any(Object),
      expect.objectContaining({ dedupKey: 'workspace-runs-fallback:pending:ws_test' }),
    );
  });

  it('renders the installed capability runs panel without starting fallback polling', async () => {
    vi.mocked(getWorkspaceToolDefinitions).mockResolvedValue([IG_RUNS_TOOL as any]);
    vi.mocked(loadCapabilityUIComponent).mockResolvedValue(function MockIGRunsWorkspaceToolPanel() {
      return <div data-testid="ig-runs-panel">IG runs panel</div>;
    });

    render(
      <WorkspaceRunsPanel
        workspaceId="ws_test"
        activeCapabilityCode="ig"
        runObservationsSummary={{
          summary: {
            workspace_id: 'ws_test',
            source_kind: 'external_runner',
            external_active_count: 1,
            counts: {},
            cards: [{ id: 'fallback_card' }],
          } as any,
          isLoading: false,
          error: null,
          externalActiveCount: 1,
        }}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('ig-runs-panel')).toBeInTheDocument();
    });

    expect(screen.queryByTestId('workspace-run-observations-panel')).not.toBeInTheDocument();
    expect(screen.queryByText('2 running · 1 pending')).not.toBeInTheDocument();
    expect(vi.mocked(sharedGetFetch)).not.toHaveBeenCalled();
    expect(vi.mocked(primeCapabilityUIComponentMetadata)).toHaveBeenCalledWith(
      'ig',
      [IG_RUNS_TOOL.panel_component],
    );
    expect(vi.mocked(loadCapabilityUIComponent)).toHaveBeenCalledWith(
      'ig',
      'IGRunsWorkspaceToolPanel',
      'http://api.test',
      'ws_test',
    );
  });
});
