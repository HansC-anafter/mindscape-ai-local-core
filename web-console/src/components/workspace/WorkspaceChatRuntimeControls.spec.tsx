import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';

import { WorkspaceMetadataProvider } from '@/contexts/WorkspaceMetadataContext';

import { WorkspaceChatRuntimeControls } from './WorkspaceChatRuntimeControls';

vi.mock('@/hooks/useChatModel', () => ({
  useChatModel: () => ({
    selectModel: vi.fn(),
  }),
}));

vi.mock('@/hooks/useWorkspaceExecutorRoute', () => ({
  useWorkspaceExecutorRoute: () => ({
    routeEntries: ['codex_cli'],
    dispatchChain: ['codex_cli'],
    resolvedRuntime: 'codex_cli',
    loading: false,
    error: null,
    refresh: vi.fn(),
    setPrimaryRuntime: vi.fn(async () => true),
    clearPrimaryRuntime: vi.fn(async () => true),
  }),
}));

vi.mock('@/components/Toast', () => ({
  useToast: () => ({
    showToast: vi.fn(),
    ToastComponent: function MockToastComponent() {
      return null;
    },
  }),
}));

describe('WorkspaceChatRuntimeControls', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url === 'http://api.test/api/v1/workspaces/ws-test/agents') {
        return new Response(
          JSON.stringify({
            agents: [
              {
                id: 'codex_cli',
                name: 'Codex CLI',
                description: 'Codex runtime',
                status: 'unavailable',
                version: '1.0.0',
                risk_level: 'medium',
                cli_command: null,
                transport: null,
                reason: 'no_ws_client',
              },
              {
                id: 'openclaw',
                name: 'openclaw',
                description: 'OpenClaw runtime',
                status: 'available',
                version: '1.0.0',
                risk_level: 'high',
                cli_command: 'openclaw',
                transport: null,
                reason: null,
              },
            ],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      if (url.includes('/system-settings/llm-models/chat')) {
        return new Response(null, { status: 200 });
      }

      return new Response(JSON.stringify({ detail: `Unhandled fetch ${url}` }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      });
    }) as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('keeps a workspace-bound codex runtime selectable even when the bridge is offline', async () => {
    render(
      <WorkspaceMetadataProvider>
        <WorkspaceChatRuntimeControls
          workspaceId="ws-test"
          apiUrl="http://api.test"
          layout="panel"
        />
      </WorkspaceMetadataProvider>,
    );

    await waitFor(() => {
      expect((screen.getAllByRole('combobox')[0] as HTMLSelectElement).value).toBe('codex_cli');
    });

    const runtimeSelect = screen.getAllByRole('combobox')[0] as HTMLSelectElement;
    expect(runtimeSelect.value).toBe('codex_cli');

    const codexOption = within(runtimeSelect).getByRole('option', {
      name: 'Codex CLI (bound)',
    }) as HTMLOptionElement;
    expect(codexOption.disabled).toBe(false);
    expect(screen.getByText(/workspace-bound, bridge offline/i)).toBeInTheDocument();
    expect(screen.getByText(/no_ws_client/i)).toBeInTheDocument();
  });
});
