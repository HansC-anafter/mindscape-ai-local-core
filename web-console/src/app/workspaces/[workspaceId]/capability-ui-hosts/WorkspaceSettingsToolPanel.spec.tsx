import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import WorkspaceSettingsToolPanel from './WorkspaceSettingsToolPanel';

const routerMock = vi.hoisted(() => ({
  push: vi.fn(),
}));
const windowOpenMock = vi.hoisted(() => vi.fn(() => ({ opener: null })));

const workspaceDataMock = vi.hoisted(() => ({
  workspace: {
    id: 'ws_test',
    title: 'Test Workspace',
    execution_mode: 'hybrid' as const,
    execution_priority: 'medium' as const,
    expected_artifacts: ['md'],
    metadata: {
      sgr_enabled: true,
      sgr_mode: 'inline',
    },
    playbook_auto_execution_config: {
      intent_extraction: {
        auto_execute: false,
        confidence_threshold: 0.8,
      },
    },
    storage_base_path: '/tmp/mindscape',
    artifacts_dir: 'artifacts',
  },
  systemStatus: {
    llm_configured: true,
    llm_provider: 'Ollama',
    vector_db_connected: true,
    tools: {
      gemini: { connected: true, status: 'connected' },
    },
    critical_issues_count: 0,
    has_issues: false,
  },
  refreshAll: vi.fn(async () => undefined),
  refreshSystemStatus: vi.fn(async () => undefined),
  refreshWorkspaceDetails: vi.fn(async () => undefined),
  updateWorkspace: vi.fn(async (updates: Record<string, unknown>) => ({
    id: 'ws_test',
    title: 'Test Workspace',
    ...updates,
  })),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => routerMock,
}));

vi.mock('@/lib/i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/i18n')>();
  return {
    ...actual,
    useLocaleContext: () => ({ locale: 'en' }),
  };
});

vi.mock('@/contexts/WorkspaceDataContext', () => ({
  useWorkspaceDataOptional: () => workspaceDataMock,
}));

vi.mock('@/lib/page-visibility', () => ({
  isDocumentHidden: () => false,
  onDocumentVisible: () => vi.fn(),
}));

vi.mock('../components/CapabilityExtensionSlot', async () => {
  const ReactModule = await import('react');
  return {
    default: function MockCapabilityExtensionSlot({
      section,
      workspaceId,
      ownerContract,
    }: {
      section: string;
      workspaceId: string;
      ownerContract?: { capabilityCode: string; componentCode: string };
    }) {
      ReactModule.useEffect(() => {
        const params = new URLSearchParams({ section, workspace_id: workspaceId });
        if (ownerContract) {
          params.set('capability_code', ownerContract.capabilityCode);
          params.set('component_code', ownerContract.componentCode);
        }
        void fetch(`/api/v1/settings/extensions?${params.toString()}`);
      }, [
        ownerContract?.capabilityCode,
        ownerContract?.componentCode,
        section,
        workspaceId,
      ]);
      return ReactModule.createElement(
        'div',
        {
          'data-testid': 'mock-capability-extension-slot',
          'data-owner-capability': ownerContract?.capabilityCode,
          'data-owner-component': ownerContract?.componentCode,
        },
        section,
      );
    },
  };
});

vi.mock('@/components/StoragePathConfigModal', () => ({
  default: function MockStoragePathConfigModal({ isOpen }: { isOpen: boolean }) {
    return isOpen ? <div data-testid="storage-path-config-modal" /> : null;
  },
}));

vi.mock('@/components/workspace/WorkspaceToolOverlayFloatingPanel', () => ({
  WorkspaceToolOverlayFloatingPanel: ({
    open,
    workspaceId,
  }: {
    open: boolean;
    workspaceId: string;
    onClose: () => void;
  }) => open ? (
    <div data-testid="mock-workspace-tool-overlay-floating-panel" data-workspace-id={workspaceId} />
  ) : null,
}));

function stubOkFetch(overrides?: {
  agentsBody?: Record<string, unknown>;
}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input);
    let body: Record<string, unknown> = { status: 'ok' };
    if (url.includes('/agents/bridge-service')) {
      body = {
        service: 'cli_bridge',
        state: 'ready',
        running: true,
        installed: true,
        supported: true,
        auto_recovery: true,
        message: 'CLI bridge LaunchAgent is running.',
      };
    } else if (url.includes('/agents')) {
      body = overrides?.agentsBody || {
        bridge_script_path: '/project/scripts/start_cli_bridge.sh',
        agents: [
          {
            id: 'codex_cli',
            name: 'Codex CLI',
            status: 'available',
            transport: 'ws',
          },
        ],
      };
    } else if (url.includes('/api/v1/host-resources/summary')) {
      body = {
        captured_at: '2026-05-16T00:00:00Z',
        degraded: false,
        pressure_state: 'ok',
        free_percent: 42,
        headroom_mb: 10240,
        reserved_mb: 7168,
        lanes: {
          busy: 1,
          blocked: 2,
          total: 5,
        },
        heavy_consumers: [
          {
            consumer_id: 'mlx:qwen',
            label: 'MLX Qwen',
            memory_mb: 7168,
            memory_source: 'declared',
          },
        ],
        primary_blockers: [
          {
            lane_id: 'lane:paused',
            label: 'Paused Lane',
            state: 'paused',
            reason: null,
          },
        ],
        route_controls: {
          active: 2,
          draining: 1,
          targets: ['comfyui_runtime:flux2', 'mlx:qwen9b'],
        },
        alerts: [
          {
            alert_id: 'host_resource_lanes_blocked',
            severity: 'warning',
            message: '2 host resource lane(s) blocked',
            action_href: '/settings?tab=runtime&section=host-resources',
          },
          {
            alert_id: 'route_drain_active',
            severity: 'info',
            message: '1 route reservation(s) draining',
            action_href: '/settings?tab=runtime&section=host-resources',
          },
        ],
        dashboard_href: '/settings?tab=runtime&section=host-resources',
      };
    } else if (url.includes('/workspace-chat')) {
      body = {
        source: 'system_settings.chat_model',
        chat_model: {
          model_name: 'llama3',
          provider: 'ollama',
          metadata: { source: 'system_settings.chat_model' },
        },
        available_chat_models: [
          { model_name: 'llama3', provider: 'ollama', description: 'Local LLM' },
        ],
      };
    } else if (url.includes('/workspace-executor')) {
      body = {
        primary_executor_runtime: null,
        resolved_executor_runtime: null,
        route_authority: 'model-route-registry',
      };
    } else if (url.includes('/api/v1/access-control/workspaces/')) {
      body = {
        scope_type: 'workspace',
        scope_id: 'ws_test',
        revision: 1,
        members: [],
        invitations: [],
        audit_events: [],
        role_catalog_version: 'workspace-access-system-roles.v1',
      };
    }
    return {
      ok: true,
      status: 200,
      json: async () => body,
    } as Response;
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

async function flushAsyncEffects() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe('WorkspaceSettingsToolPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('open', windowOpenMock);
    workspaceDataMock.updateWorkspace.mockImplementation(async (updates: Record<string, unknown>) => ({
      id: 'ws_test',
      title: 'Test Workspace',
      ...updates,
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('loads the status snapshot once without registering a polling interval', async () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');
    const fetchMock = stubOkFetch();

    render(<WorkspaceSettingsToolPanel workspaceId="ws_test" apiUrl="http://api.test" />);

    expect(screen.getByTestId('workspace-settings-section-stack')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Status/ })).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('button', { name: /Workspace/ })).toHaveAttribute('aria-expanded', 'false');
    await flushAsyncEffects();
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(setIntervalSpy).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/v1/workspaces/ws_test/agents');
    expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/v1/host/services/xtts/health');
    expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/v1/host/services/mcp-gateway/health');
    expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/v1/host-resources/summary?allow_stale=true');
    expect(workspaceDataMock.refreshSystemStatus).not.toHaveBeenCalled();
  });

  it('renders CLI bridge guidance from the workspace agents snapshot without polling', async () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');
    stubOkFetch({
      agentsBody: {
        bridge_script_path: '/project/scripts/start_cli_bridge.sh',
        agents: [
          {
            id: 'codex_cli',
            name: 'Codex CLI',
            status: 'unavailable',
            reason: 'no_ws_client',
          },
        ],
      },
    });

    render(<WorkspaceSettingsToolPanel workspaceId="ws_test" apiUrl="http://api.test" />);

    await flushAsyncEffects();
    expect(screen.getByText('0/1 connected')).toBeInTheDocument();
    expect(screen.getByText('Codex CLI')).toBeInTheDocument();
    expect(screen.getByText('Start Bridge')).toBeInTheDocument();
    expect(setIntervalSpy).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'How to connect CLI bridge' }));

    expect(screen.getByRole('dialog', { name: 'Workspace CLI Bridge' })).toBeInTheDocument();
    await flushAsyncEffects();
    expect(screen.getByText('CLI bridge LaunchAgent is running.')).toBeInTheDocument();
    expect(screen.getByText('/project/scripts/start_cli_bridge.sh --all')).toBeInTheDocument();
    expect(screen.getByText('/project/scripts/start_cli_bridge.sh --workspace-id ws_test')).toBeInTheDocument();
    expect(screen.getByText((text) => text.includes('start_cli_bridge.ps1 -All'))).toBeInTheDocument();
    expect(screen.getByText((text) => text.includes('start_cli_bridge.ps1 -WorkspaceId ws_test'))).toBeInTheDocument();
    expect(setIntervalSpy).not.toHaveBeenCalled();
  });

  it('renders host resources summary in the Status section and opens the full dashboard', async () => {
    stubOkFetch();

    render(<WorkspaceSettingsToolPanel workspaceId="ws_test" apiUrl="http://api.test" />);

    await waitFor(() => {
      expect(screen.getByText('1 busy / 2 blocked / 5 total lanes')).toBeInTheDocument();
    });
    expect(screen.getByText('Host Resources')).toBeInTheDocument();
    expect(screen.getByTestId('host-resource-status-summary')).toHaveTextContent('ok');
    expect(screen.getByText('Top: MLX Qwen 7,168 MB')).toBeInTheDocument();
    expect(screen.getByText('Reservations: 2 active / 1 drain')).toBeInTheDocument();
    expect(screen.getByText('2 host resource lane(s) blocked')).toBeInTheDocument();
    expect(screen.getByText('1 route reservation(s) draining')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Open dashboard/ }));

    expect(windowOpenMock).toHaveBeenCalledWith(
      '/settings?tab=runtime&section=host-resources&workspace_id=ws_test',
      '_blank',
      'noopener,noreferrer',
    );
    expect(routerMock.push).not.toHaveBeenCalled();
  });

  it('uses refresh=true for host resources only when the Status refresh button is clicked', async () => {
    const fetchMock = stubOkFetch();

    render(<WorkspaceSettingsToolPanel workspaceId="ws_test" apiUrl="http://api.test" />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/v1/host-resources/summary?allow_stale=true');
    });

    fireEvent.click(screen.getByRole('button', { name: 'Refresh status' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('http://api.test/api/v1/host-resources/summary?refresh=true');
    });
    expect(workspaceDataMock.refreshAll).toHaveBeenCalled();
  });

  it('keeps tool engine extension panels cold until the Tools section is expanded', async () => {
    const fetchMock = stubOkFetch();

    render(<WorkspaceSettingsToolPanel workspaceId="ws_test" apiUrl="http://api.test" />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(4);
    });
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/api/v1/settings/extensions'))).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: /Tools/ }));

    await waitFor(() => {
      expect(screen.getByTestId('mock-capability-extension-slot')).toHaveTextContent('runtime-environments');
    });
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/settings/extensions?section=runtime-environments&workspace_id=ws_test');
    expect(screen.queryByTestId('mock-workspace-tool-overlay-floating-panel')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Open Tool Overlay' }));

    expect(screen.getByTestId('mock-workspace-tool-overlay-floating-panel')).toHaveAttribute('data-workspace-id', 'ws_test');
  });

  it('adds Members & access as the seventh cold host editor with one pack diagnostic slot', async () => {
    const fetchMock = stubOkFetch();

    render(<WorkspaceSettingsToolPanel workspaceId="ws_test" apiUrl="http://api.test" />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    const stack = screen.getByTestId('workspace-settings-section-stack');
    expect(stack.children).toHaveLength(7);
    expect(stack.lastElementChild).toHaveAttribute('data-testid', 'workspace-settings-section-members-access');
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/api/v1/settings/extensions'))).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: /Members & access/ }));

    await waitFor(() => {
      expect(screen.getByTestId('access-scope-management')).toBeInTheDocument();
      expect(screen.getByTestId('mock-capability-extension-slot')).toHaveTextContent('remote-workbench-workspace-access');
    });
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/settings/extensions?section=remote-workbench-workspace-access&workspace_id=ws_test&capability_code=mindscape_cloud_integration&component_code=MindscapeRemoteWorkbenchWorkspaceAccessPanel');
    const slot = screen.getByTestId('mock-capability-extension-slot');
    expect(slot).toHaveAttribute('data-owner-capability', 'mindscape_cloud_integration');
    expect(slot).toHaveAttribute('data-owner-component', 'MindscapeRemoteWorkbenchWorkspaceAccessPanel');
  });

  it('loads workspace-scoped social media provider settings only from the Social section', async () => {
    const fetchMock = stubOkFetch();

    render(<WorkspaceSettingsToolPanel workspaceId="ws_test" apiUrl="http://api.test" />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(4);
    });
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/api/v1/settings/extensions'))).toBe(false);

    fireEvent.click(screen.getByRole('button', { name: /Social/ }));

    await waitFor(() => {
      expect(screen.getByTestId('mock-capability-extension-slot')).toHaveTextContent('social-media:youtube');
    });
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/settings/extensions?section=social-media%3Ayoutube&workspace_id=ws_test');
  });

  it('treats workspace execution as LLM model routing, not tool runtime extensions', async () => {
    const fetchMock = stubOkFetch();

    render(<WorkspaceSettingsToolPanel workspaceId="ws_test" apiUrl="http://api.test" />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(4);
    });

    fireEvent.click(screen.getByRole('button', { name: /Execution/ }));

    await waitFor(() => {
      expect(screen.getByTestId('workspace-settings-execution-section')).toBeInTheDocument();
    });
    expect(screen.getByText('Workspace Execution')).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url]) => (
      String(url) === 'http://api.test/api/v1/settings/model-route-registry/workspace-chat?workspace_id=ws_test&profile_id=default-user'
    ))).toBe(true);
    expect(fetchMock.mock.calls.some(([url]) => (
      String(url) === 'http://api.test/api/v1/settings/model-route-registry/workspace-executor?workspace_id=ws_test'
    ))).toBe(true);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/api/v1/settings/extensions'))).toBe(false);
  });

  it('mounts the data source modal only after explicit user activation', async () => {
    stubOkFetch();

    render(<WorkspaceSettingsToolPanel workspaceId="ws_test" apiUrl="http://api.test" />);

    const dataSectionButton = screen.getByTestId('workspace-settings-section-data').querySelector('button') as HTMLButtonElement;
    fireEvent.click(dataSectionButton);
    expect(dataSectionButton).toHaveAttribute('aria-expanded', 'true');
    expect(screen.queryByTestId('storage-path-config-modal')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Open Data Sources' }));

    await waitFor(() => {
      expect(screen.getByTestId('storage-path-config-modal')).toBeInTheDocument();
    });
  });

  it('saves workspace settings without adding a writable meeting_enabled field', async () => {
    const fetchMock = stubOkFetch();

    render(<WorkspaceSettingsToolPanel workspaceId="ws_test" apiUrl="http://api.test" />);

    fireEvent.click(screen.getByRole('button', { name: /Workspace/ }));
    expect(screen.getByRole('button', { name: /Workspace/ })).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(workspaceDataMock.updateWorkspace).toHaveBeenCalled();
    });
    expect(workspaceDataMock.updateWorkspace.mock.calls[0][0]).not.toHaveProperty('meeting_enabled');

    const patchCall = fetchMock.mock.calls.find(([url]) => (
      String(url).includes('/api/v1/workspaces/ws_test/playbook-auto-exec-config')
    ));
    expect(patchCall).toBeTruthy();
    const patchBody = JSON.parse(String((patchCall?.[1] as RequestInit | undefined)?.body || '{}'));
    expect(patchBody).not.toHaveProperty('meeting_enabled');
  });
});
