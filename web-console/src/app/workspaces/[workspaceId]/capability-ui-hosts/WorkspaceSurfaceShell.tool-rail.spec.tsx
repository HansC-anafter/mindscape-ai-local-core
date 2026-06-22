import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import './WorkspaceSurfaceShell.test-support';
import { loadCapabilityUIComponent } from '@/lib/capability-ui-loader';
import { fetchWorkspaceToolDefinitions } from '@/lib/workspace-tools/workspace-tool-registry';
import { useRunObservationsSummary } from '@/lib/workspace-runs/useRunObservationsSummary';
import WorkspaceSurfaceShell from './WorkspaceSurfaceShell';

describe('WorkspaceSurfaceShell tool rail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchWorkspaceToolDefinitions).mockResolvedValue([]);
    vi.mocked(loadCapabilityUIComponent).mockResolvedValue(null);
    vi.mocked(useRunObservationsSummary).mockReturnValue({
      summary: null,
      isLoading: false,
      error: null,
      externalActiveCount: 0,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('opens the built-in runs panel without loading AOL shell panels', () => {
    render(
      <WorkspaceSurfaceShell
        workspaceId="ws_test"
        activeCapabilityCode="demo_capability"
        surfacePath={[]}
      >
        <div data-testid="surface-content">Capability surface</div>
      </WorkspaceSurfaceShell>,
    );

    fireEvent.click(screen.getByTestId('workspace-runs-tool'));

    expect(screen.getByTestId('workspace-global-tool-panel')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-global-tool-panel')).toHaveAttribute('data-active-tool-key', 'core:runs_panel');
    expect(screen.getByTestId('workspace-global-tool-panel')).toHaveClass('w-80');
    expect(screen.getByTestId('workspace-global-tool-panel').querySelector('.overflow-y-auto')).not.toBeNull();
    return waitFor(() => {
      expect(screen.getByText('ig_complete_workflow')).toBeInTheDocument();
      expect(screen.getByTestId('aol-workspace-region')).toHaveAttribute(
        'data-aol-panel-loaded',
        'idle',
      );
    }, { timeout: 10000 });
  });

  it('keeps external runner summary cold while the runs panel is closed', () => {
    vi.mocked(useRunObservationsSummary).mockReturnValue({
      summary: {
        workspace_id: 'ws_test',
        source_kind: 'external_runner',
        external_active_count: 2,
        counts: { running: 2 },
        cards: [],
      },
      isLoading: false,
      error: null,
      externalActiveCount: 2,
    });

    render(
      <WorkspaceSurfaceShell
        workspaceId="ws_test"
        activeCapabilityCode="demo_capability"
        surfacePath={[]}
      >
        <div data-testid="surface-content">Capability surface</div>
      </WorkspaceSurfaceShell>,
    );

    expect(screen.getByTestId('workspace-runs-tool')).toHaveTextContent('1');
    expect(useRunObservationsSummary).not.toHaveBeenCalled();
  });

  it('opens the built-in settings panel at the contract width with a scrollable body', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok' }),
    } as Response);

    render(
      <WorkspaceSurfaceShell
        workspaceId="ws_test"
        activeCapabilityCode="demo_capability"
        surfacePath={[]}
      >
        <div data-testid="surface-content">Capability surface</div>
      </WorkspaceSurfaceShell>,
    );

    fireEvent.click(screen.getByTestId('workspace-settings-tool'));

    expect(screen.getByTestId('workspace-global-tool-panel')).toHaveAttribute('data-active-tool-key', 'core:settings');
    expect(screen.getByTestId('workspace-global-tool-panel')).toHaveClass('w-80');
    await waitFor(() => {
      expect(screen.getByTestId('workspace-settings-panel')).toBeInTheDocument();
    }, { timeout: 10000 });
    expect(screen.getByTestId('workspace-settings-panel-body')).toHaveClass('overflow-y-auto');
    expect(screen.queryByTestId('workspace-settings-tool-engine-extensions')).not.toBeInTheDocument();
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith('http://api.test/api/v1/workspaces/ws_test/agents');
      expect(fetchSpy).toHaveBeenCalledWith('http://api.test/api/v1/host/services/xtts/health');
      expect(fetchSpy).toHaveBeenCalledWith('http://api.test/api/v1/host/services/mcp-gateway/health');
      expect(fetchSpy).toHaveBeenCalledWith('http://api.test/api/v1/host-resources/summary?allow_stale=true');
    });
    expect(screen.getByTestId('aol-workspace-region')).toHaveAttribute(
      'data-aol-panel-loaded',
      'idle',
    );
  });

  it('opens and closes the built-in pack panel on the right rail', async () => {
    render(
      <WorkspaceSurfaceShell
        workspaceId="ws_test"
        activeCapabilityCode="demo_capability"
        surfacePath={[]}
      >
        <div data-testid="surface-content">Capability surface</div>
      </WorkspaceSurfaceShell>,
    );

    expect(screen.queryByTestId('workspace-global-tool-panel')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('workspace-pack-tool'));

    expect(screen.getByTestId('workspace-global-tool-panel')).toHaveAttribute('data-active-tool-key', 'core:pack');
    expect(screen.getByTestId('workspace-global-tool-panel')).toHaveClass('w-80');
    expect(screen.getByTestId('workspace-global-tool-panel').querySelector('.overflow-y-auto')).not.toBeNull();
    await waitFor(() => {
      expect(screen.getByTestId('workspace-pack-tool-panel')).toHaveTextContent('Pack panel ws_test');
    });

    fireEvent.click(screen.getByRole('button', { name: 'Close Pack' }));
    expect(screen.queryByTestId('workspace-global-tool-panel')).not.toBeInTheDocument();
  });

  it('keeps IG run APIs cold until the runs rail tool is opened', async () => {
    vi.mocked(fetchWorkspaceToolDefinitions).mockResolvedValue([
      {
        tool_key: 'ig:runs_panel',
        capability_code: 'ig',
        id: 'runs_panel',
        group: 'capability',
        slot: 'workspace.right_rail.tool',
        label: 'Runs',
        icon: 'Activity',
        order: 10,
        panel_component_code: 'IGRunsWorkspaceToolPanel',
        panel_component: {
          code: 'IGRunsWorkspaceToolPanel',
          path: 'ui/IGRunsWorkspaceToolPanel.tsx',
          description: 'Runs panel',
          export: 'default',
          artifact_types: [],
          playbook_codes: [],
          import_path: '@/app/capabilities/ig/components/IGRunsWorkspaceToolPanel',
          layout_hint: 'default',
        },
      },
    ]);
    const ReactModule = await import('react');
    vi.mocked(loadCapabilityUIComponent).mockResolvedValue(function MockIGRunsWorkspaceToolPanel({
      workspaceId,
    }: {
      workspaceId: string;
    }) {
      ReactModule.useEffect(() => {
        void fetch(`/api/v1/ig/workbench/sidebar-summary?workspace_id=${workspaceId}`);
      }, [workspaceId]);
      return ReactModule.createElement('div', { 'data-testid': 'ig-runs-adapter' }, 'IG runs');
    });
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({}),
    } as Response);

    render(
      <WorkspaceSurfaceShell
        workspaceId="ws_ig"
        activeCapabilityCode="ig"
        surfacePath={[]}
      >
        <div data-testid="surface-content">IG workbench</div>
      </WorkspaceSurfaceShell>,
    );

    expect(fetchSpy).not.toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/ig/workbench/sidebar-summary'),
    );

    fireEvent.click(screen.getByTestId('workspace-runs-tool'));

    await waitFor(() => {
      expect(screen.getByTestId('ig-runs-adapter')).toBeInTheDocument();
      expect(fetchSpy).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/ig/workbench/sidebar-summary'),
      );
    });
    expect(screen.getByTestId('aol-workspace-region')).toHaveAttribute(
      'data-aol-panel-loaded',
      'idle',
    );
  });
});
