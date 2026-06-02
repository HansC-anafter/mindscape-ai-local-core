import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { WorkspaceExecutionSettingsControls } from './WorkspaceExecutionSettingsControls';

const setPrimaryRuntimeMock = vi.hoisted(() => vi.fn(async () => false));
const clearPrimaryRuntimeMock = vi.hoisted(() => vi.fn(async () => true));
const refreshAgentsMock = vi.hoisted(() => vi.fn(async () => undefined));
const windowOpenMock = vi.hoisted(() => vi.fn());

vi.mock('@/contexts/WorkspaceDataContext', () => ({
  useWorkspaceDataOptional: () => ({
    systemStatus: {
      llm_provider: 'Ollama',
    },
  }),
}));

vi.mock('@/hooks/useWorkspaceExecutorRoute', () => ({
  useWorkspaceExecutorRoute: () => ({
    routeEntries: ['codex_cli'],
    resolvedRuntime: 'codex_cli',
    loading: false,
    error: null,
    setPrimaryRuntime: setPrimaryRuntimeMock,
    clearPrimaryRuntime: clearPrimaryRuntimeMock,
  }),
}));

vi.mock('@/hooks/useWorkspaceAgentsSnapshot', () => ({
  useWorkspaceAgentsSnapshot: () => ({
    agents: [
      {
        id: 'codex_cli',
        name: 'Codex CLI',
        status: 'unavailable',
        reason: 'no_ws_client',
      },
      {
        id: 'openclaw',
        name: 'OpenClaw',
        status: 'available',
        reason: null,
      },
    ],
    loading: false,
    error: null,
    refresh: refreshAgentsMock,
  }),
}));

vi.mock('@/lib/page-visibility', () => ({
  isDocumentHidden: () => false,
  onDocumentVisible: () => vi.fn(),
}));

vi.mock('./WorkspaceRuntimeCliFloatingPanel', () => ({
  WorkspaceRuntimeCliFloatingPanel: ({
    open,
    workspaceId,
    onClose,
  }: {
    open: boolean;
    workspaceId: string;
    onClose: () => void;
  }) => open ? (
    <div data-testid="mock-workspace-runtime-cli-floating-panel" data-workspace-id={workspaceId}>
      <button type="button" onClick={onClose}>Close Runtime CLI</button>
    </div>
  ) : null,
}));

vi.mock('./WorkspaceRuntimeProfileFloatingPanel', () => ({
  WorkspaceRuntimeProfileFloatingPanel: ({
    open,
    workspaceId,
    apiUrl,
  }: {
    open: boolean;
    workspaceId: string;
    apiUrl: string;
    onClose: () => void;
  }) => open ? (
    <div
      data-testid="mock-workspace-runtime-profile-floating-panel"
      data-workspace-id={workspaceId}
      data-api-url={apiUrl}
    />
  ) : null,
}));

describe('WorkspaceExecutionSettingsControls', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('open', windowOpenMock);
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/workspace-chat')) {
        return new Response(JSON.stringify({
          source: 'system_settings.chat_model',
          chat_model: {
            model_name: 'llama3',
            provider: 'ollama',
            metadata: { source: 'system_settings.chat_model' },
          },
          available_chat_models: [
            { model_name: 'llama3', provider: 'ollama', description: 'Local LLM' },
          ],
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      return new Response(JSON.stringify({ detail: `Unhandled fetch ${url}` }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      });
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('shows a workspace-bound offline executor without registering polling', async () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');

    render(<WorkspaceExecutionSettingsControls workspaceId="ws_test" apiUrl="http://api.test" />);

    expect(screen.getByText('Codex CLI')).toBeInTheDocument();
    expect(screen.getByText(/workspace-bound, bridge offline/i)).toBeInTheDocument();
    expect(screen.getByText(/no_ws_client/i)).toBeInTheDocument();
    expect(setIntervalSpy).not.toHaveBeenCalled();
  });

  it('restores the resolved executor selection when a runtime update fails', async () => {
    render(<WorkspaceExecutionSettingsControls workspaceId="ws_test" apiUrl="http://api.test" />);

    const selector = await screen.findByTestId('workspace-executor-runtime-selector');
    const runtimeSelect = within(selector).getByRole('combobox', {
      name: 'Workspace Executor',
    }) as HTMLSelectElement;
    expect(runtimeSelect.value).toBe('codex_cli');

    fireEvent.change(runtimeSelect, { target: { value: 'openclaw' } });

    await waitFor(() => {
      expect(setPrimaryRuntimeMock).toHaveBeenCalledWith('openclaw');
    });
    await waitFor(() => {
      expect(runtimeSelect.value).toBe('codex_cli');
    });
    expect(screen.getByText('Executor update failed')).toBeInTheDocument();
  });

  it('opens Runtime CLI account homes in a workspace floating panel instead of a settings page', async () => {
    render(<WorkspaceExecutionSettingsControls workspaceId="ws_test" apiUrl="http://api.test" />);

    expect(screen.getByText('Manage workspace Codex account homes')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Runtime CLI Accounts/ }));

    expect(screen.getByTestId('mock-workspace-runtime-cli-floating-panel')).toHaveAttribute('data-workspace-id', 'ws_test');
    expect(windowOpenMock).not.toHaveBeenCalled();
  });

  it('opens Runtime Profile in a workspace floating panel', async () => {
    render(<WorkspaceExecutionSettingsControls workspaceId="ws_test" apiUrl="http://api.test" />);

    expect(screen.getByText('Manage workspace execution contracts')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Runtime Profile/ }));

    expect(screen.getByTestId('mock-workspace-runtime-profile-floating-panel')).toHaveAttribute('data-workspace-id', 'ws_test');
    expect(screen.getByTestId('mock-workspace-runtime-profile-floating-panel')).toHaveAttribute('data-api-url', 'http://api.test');
    expect(windowOpenMock).not.toHaveBeenCalled();
  });
});
