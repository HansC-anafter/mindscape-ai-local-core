import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { loadCapabilityUIComponent } from '@/lib/capability-ui-loader';
import { KeyboardShortcutProvider } from '@/lib/keyboard-shortcuts';
import { fetchWorkspaceToolDefinitions } from '@/lib/workspace-tools/workspace-tool-registry';
import { useRunObservationsSummary } from '@/lib/workspace-runs/useRunObservationsSummary';
import {
  useCapabilityWorkbenchInfoMetadataRegistration,
} from '@/components/capabilities/workbench/CapabilityWorkbenchInfoProvider';
import type { CapabilityWorkbenchInfoMetadata } from '@/types/capability-workbench';
import WorkspaceSurfaceShell from './WorkspaceSurfaceShell';

vi.mock('@/lib/api-url', () => ({
  getApiBaseUrl: () => 'http://api.test',
}));

vi.mock('@/lib/page-visibility', () => ({
  isDocumentHidden: () => false,
}));

vi.mock('@/lib/i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/i18n')>();
  return {
    ...actual,
    useT: () => ((key: string) => (key === 'workspacePackTool' ? 'Pack' : null)),
  };
});

vi.mock('next/navigation', () => ({
  usePathname: () => '/workspaces/ws_test/capability-ui-hosts/demo_capability',
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

vi.mock('./WorkspacePackToolPanel', async () => {
  const ReactModule = await import('react');
  return {
    default: ({ workspaceId }: { workspaceId: string }) => ReactModule.createElement(
      'div',
      { 'data-testid': 'workspace-pack-tool-panel' },
      `Pack panel ${workspaceId}`,
    ),
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

const WORKBENCH_METADATA: CapabilityWorkbenchInfoMetadata = {
  schemaVersion: 'capability_workbench_info_metadata.v1',
  capability: {
    code: 'demo_capability',
    label: 'Demo Capability',
  },
  workspace: {
    id: 'ws_test',
  },
  primaryObject: {
    kind: 'artifact',
    id: 'asset_test',
    label: 'Asset test',
  },
  session: {
    id: 'session_route_001',
    kind: 'demo_session',
    status: 'active',
  },
  artifact: {
    id: 'artifact_test',
    kind: 'demo_artifact',
  },
  selection: {
    sceneId: 'item01',
    mode: 'inspect',
    department: 'review',
  },
  references: [
    {
      key: 'asset',
      label: 'Asset',
      value: 'asset_test',
      copyValue: 'asset_test',
    },
  ],
  status: [
    {
      key: 'preview_state',
      label: 'Preview state',
      value: 'idle',
      tone: 'neutral',
    },
  ],
};

function WorkbenchMetadataRegistration() {
  useCapabilityWorkbenchInfoMetadataRegistration(WORKBENCH_METADATA);
  return <div data-testid="surface-content">Capability surface</div>;
}

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
        activeCapabilityCode="demo_capability"
        surfacePath={['sessions', 'session_route_001']}
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
      'demo_capability',
    );
    expect(screen.getByTestId('workspace-surface-shell')).toHaveAttribute(
      'data-surface-path',
      'sessions/session_route_001',
    );
    expect(screen.getByTestId('surface-content')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-global-tool-rail')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-runs-tool')).toHaveTextContent('1');
    expect(document.querySelector('[data-workspace-tool-rail="true"]')).not.toBeNull();
    await waitFor(() => {
      expect(screen.getByTestId('workspace-info-tool')).toBeDisabled();
    });
    expect(screen.getByTestId('workspace-info-tool')).toHaveAttribute('title', 'Info (Q)');
    expect(screen.getByTestId('workspace-settings-tool')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-pack-tool')).toBeInTheDocument();
    expect(screen.getByTestId('aol-global-anchor')).toBeInTheDocument();
    expect(screen.getByTestId('aol-runtime-flow-anchor')).toBeInTheDocument();
    expect(screen.getByTestId('aol-workspace-region')).toHaveAttribute(
      'data-aol-panel-loaded',
      'idle',
    );
    expect(screen.queryByTestId('workspace-global-tool-panel')).not.toBeInTheDocument();
  });

  it('keeps manifest shortcuts on workspace right-rail tools', async () => {
    vi.mocked(fetchWorkspaceToolDefinitions).mockResolvedValue([
      {
        tool_key: 'shortcut_capability:inspector',
        capability_code: 'shortcut_capability',
        id: 'inspector',
        group: 'capability',
        slot: 'workspace.right_rail.tool',
        label: 'Inspector',
        icon: 'PanelRight',
        order: 30,
        shortcut: 'E',
        panel_component_code: 'IGInspectorWorkspaceToolPanel',
        panel_component: {
          code: 'IGInspectorWorkspaceToolPanel',
          path: 'ui/IGInspectorWorkspaceToolPanel.tsx',
          description: 'Inspector panel',
          export: 'default',
          artifact_types: [],
          playbook_codes: [],
          import_path: '@/app/capabilities/ig/components/IGInspectorWorkspaceToolPanel',
          layout_hint: 'default',
        },
      },
    ]);

    render(
      <WorkspaceSurfaceShell
        workspaceId="ws_shortcut_capability"
        activeCapabilityCode="shortcut_capability"
        surfacePath={[]}
      >
        <div data-testid="surface-content">IG workbench</div>
      </WorkspaceSurfaceShell>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('workspace-tool-shortcut_capability:inspector')).toHaveAttribute('title', 'Inspector (E)');
    }, { timeout: 4000 });
  });

  it('toggles AOL object selection from the runtime rail shortcut', async () => {
    render(
      <KeyboardShortcutProvider loadProfileOnMount={false}>
        <WorkspaceSurfaceShell
          workspaceId="ws_test"
          activeCapabilityCode="demo_capability"
          surfacePath={[]}
        >
          <input data-testid="aol-shortcut-input" />
        </WorkspaceSurfaceShell>
      </KeyboardShortcutProvider>,
    );

    fireEvent.keyDown(screen.getByTestId('aol-shortcut-input'), { key: 'b' });
    expect(screen.getByTestId('aol-workspace-region')).toHaveAttribute('data-aol-mode', 'idle');

    fireEvent.keyDown(window, { key: 'b' });
    await waitFor(() => {
      expect(screen.getByTestId('aol-workspace-region')).toHaveAttribute('data-aol-mode', 'selecting');
    });

    fireEvent.keyDown(window, { key: 'b' });
    await waitFor(() => {
      expect(screen.getByTestId('aol-workspace-region')).toHaveAttribute('data-aol-mode', 'idle');
    });
  });

  it('opens the shared workbench info panel when the capability registers metadata', async () => {
    render(
      <WorkspaceSurfaceShell
        workspaceId="ws_test"
        activeCapabilityCode="demo_capability"
        surfacePath={['sessions', 'session_route_001']}
      >
        <WorkbenchMetadataRegistration />
      </WorkspaceSurfaceShell>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('workspace-info-tool')).not.toBeDisabled();
    });

    fireEvent.click(screen.getByTestId('workspace-info-tool'));

    expect(screen.getByTestId('workspace-global-tool-panel')).toHaveAttribute(
      'data-active-tool-key',
      'workspace-surface:demo_capability:workbench-info',
    );
    expect(screen.getByTestId('capability-workbench-info-panel')).toHaveTextContent('Demo Capability');
    expect(screen.getByText('artifact:asset_test')).toBeInTheDocument();
    expect(screen.getByText('inspect / review / item01')).toBeInTheDocument();
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
