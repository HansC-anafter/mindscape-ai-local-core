import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { loadCapabilityUIComponent } from '@/lib/capability-ui-loader';
import { fetchWorkspaceToolDefinitions } from '@/lib/workspace-tools/workspace-tool-registry';
import { useRunObservationsSummary } from '@/lib/workspace-runs/useRunObservationsSummary';
import WorkspaceSurfaceShell from './WorkspaceSurfaceShell';

vi.mock('@/lib/api-url', () => ({
  getApiBaseUrl: () => 'http://api.test',
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/workspaces/ws_test/capability-ui-hosts/performance_direction',
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/workspace-tools/workspace-tool-registry', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/workspace-tools/workspace-tool-registry')>();
  return {
    ...actual,
    fetchWorkspaceToolDefinitions: vi.fn(async () => []),
  };
});

vi.mock('@/lib/capability-ui-loader', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/capability-ui-loader')>();
  const ReactModule = await import('react');
  return {
    ...actual,
    loadCapabilityUIComponent: vi.fn(async () => function MockIGRunsWorkspaceToolPanel({
      workspaceId,
    }: {
      workspaceId: string;
    }) {
      ReactModule.useEffect(() => {
        void fetch(`/api/v1/ig/workbench/sidebar-summary?workspace_id=${workspaceId}`);
      }, [workspaceId]);
      return ReactModule.createElement('div', { 'data-testid': 'ig-runs-adapter' }, 'IG runs');
    }),
  };
});

vi.mock('@/lib/workspace-runs/useRunObservationsSummary', () => ({
  useRunObservationsSummary: vi.fn(() => ({
    summary: null,
    isLoading: false,
    error: null,
    externalActiveCount: 0,
  })),
}));

vi.mock('@/contexts/WorkspaceDataContext', () => ({
  WorkspaceDataProvider: ({
    children,
    initialLoadProfile,
  }: {
    children: React.ReactNode;
    initialLoadProfile?: string;
  }) => (
    <div data-testid="workspace-data-provider" data-initial-load-profile={initialLoadProfile || 'full'}>
      {children}
    </div>
  ),
  useWorkspaceDataOptional: () => ({
    executions: [
      {
        id: 'exec_running',
        status: 'running',
        playbook_code: 'ig_complete_workflow',
      },
      {
        id: 'exec_done',
        status: 'completed',
        playbook_code: 'ig_post_generation',
      },
    ],
  }),
}));

vi.mock('@/contexts/ExecutionContextContext', () => ({
  ExecutionContextProvider: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="execution-context-provider">{children}</div>
  ),
}));

describe('WorkspaceSurfaceShell', () => {
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
  });

  it('composes workspace providers with the generic rail for canonical capability hosts', async () => {
    render(
      <WorkspaceSurfaceShell
        workspaceId="ws_test"
        activeCapabilityCode="performance_direction"
        surfacePath={['sessions', 'ds_route_001']}
      >
        <div data-testid="surface-content">Capability surface</div>
      </WorkspaceSurfaceShell>,
    );

    expect(screen.getByTestId('workspace-data-provider')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-data-provider')).toHaveAttribute(
      'data-initial-load-profile',
      'capability-host',
    );
    expect(screen.getByTestId('execution-context-provider')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-surface-shell')).toHaveAttribute(
      'data-active-capability-code',
      'performance_direction',
    );
    expect(screen.getByTestId('workspace-surface-shell')).toHaveAttribute(
      'data-surface-path',
      'sessions/ds_route_001',
    );
    expect(screen.getByTestId('surface-content')).toBeInTheDocument();
    expect(screen.getByTestId('aol-shell-rail')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-runs-tool')).toHaveTextContent('1');
    expect(document.querySelector('[data-workspace-tool-rail="true"]')).not.toBeNull();
    expect(screen.getByTestId('workspace-settings-tool')).toBeInTheDocument();
    expect(screen.getByTestId('aol-workspace-region')).toHaveAttribute(
      'data-aol-panel-loaded',
      'idle',
    );
    expect(screen.queryByTestId('workspace-runs-panel')).not.toBeInTheDocument();
    expect(screen.queryByTestId('workspace-settings-aside')).not.toBeInTheDocument();
    expect(fetchWorkspaceToolDefinitions).not.toHaveBeenCalled();
  });

  it('opens the built-in runs panel without loading AOL shell panels', () => {
    render(
      <WorkspaceSurfaceShell
        workspaceId="ws_test"
        activeCapabilityCode="performance_direction"
        surfacePath={[]}
      >
        <div data-testid="surface-content">Capability surface</div>
      </WorkspaceSurfaceShell>,
    );

    fireEvent.click(screen.getByTestId('workspace-runs-tool'));

    expect(screen.getByTestId('workspace-runs-panel')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-runs-panel')).toHaveClass('w-80');
    expect(screen.getByTestId('workspace-runs-panel').querySelector('.overflow-y-auto')).not.toBeNull();
    return waitFor(() => {
      expect(screen.getByText('ig_complete_workflow')).toBeInTheDocument();
      expect(screen.getByTestId('aol-workspace-region')).toHaveAttribute(
        'data-aol-panel-loaded',
        'idle',
      );
    });
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
        activeCapabilityCode="performance_direction"
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
        activeCapabilityCode="performance_direction"
        surfacePath={[]}
      >
        <div data-testid="surface-content">Capability surface</div>
      </WorkspaceSurfaceShell>,
    );

    fireEvent.click(screen.getByTestId('workspace-settings-tool'));

    expect(screen.getByTestId('workspace-settings-aside')).toHaveClass('w-80');
    await waitFor(() => {
      expect(screen.getByTestId('workspace-settings-panel')).toBeInTheDocument();
    });
    expect(screen.getByTestId('workspace-settings-panel-body')).toHaveClass('overflow-y-auto');
    expect(screen.queryByTestId('workspace-settings-tool-engine-extensions')).not.toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledWith('http://api.test/api/v1/workspaces/ws_test/agents');
    expect(fetchSpy).toHaveBeenCalledWith('http://api.test/api/v1/host/services/xtts/health');
    expect(fetchSpy).toHaveBeenCalledWith('http://api.test/api/v1/host/services/mcp-gateway/health');
    expect(screen.getByTestId('aol-workspace-region')).toHaveAttribute(
      'data-aol-panel-loaded',
      'idle',
    );
  });

  it('keeps IG run APIs cold until the runs rail tool is opened', async () => {
    vi.mocked(fetchWorkspaceToolDefinitions).mockResolvedValue([
      {
        tool_key: 'ig:runs_panel',
        capability_code: 'ig',
        id: 'runs_panel',
        group: 'capability',
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
