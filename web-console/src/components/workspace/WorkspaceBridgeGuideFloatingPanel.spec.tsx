import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { WorkspaceBridgeGuideFloatingPanel } from './WorkspaceBridgeGuideFloatingPanel';

function stubBridgeFetch(body: Record<string, unknown> = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => ({
    ok: true,
    status: 200,
    json: async () => ({
      service: 'cli_bridge',
      state: 'ready',
      running: true,
      installed: true,
      supported: true,
      auto_recovery: true,
      message: 'CLI bridge LaunchAgent is running.',
      ...body,
    }),
  } as Response));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('WorkspaceBridgeGuideFloatingPanel', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders bridge commands from the workspace agents response path', async () => {
    const fetchMock = stubBridgeFetch();

    render(
      <WorkspaceBridgeGuideFloatingPanel
        open
        workspaceId="ws_test"
        apiUrl="http://api.test"
        bridgeScriptPath="/project/scripts/start_cli_bridge.sh"
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByRole('dialog', { name: 'Workspace CLI Bridge' })).toBeInTheDocument();
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        'http://api.test/api/v1/workspaces/ws_test/agents/bridge-service',
        { cache: 'no-store' },
      );
    });
    expect(screen.getByText('/project/scripts/start_cli_bridge.sh --all')).toBeInTheDocument();
    expect(screen.getByText('/project/scripts/start_cli_bridge.sh --workspace-id ws_test')).toBeInTheDocument();
    expect(screen.getByText((text) => text.includes('start_cli_bridge.ps1 -All'))).toBeInTheDocument();
    expect(screen.getByText((text) => text.includes('start_cli_bridge.ps1 -WorkspaceId ws_test'))).toBeInTheDocument();
  });

  it('falls back to the repo-relative Unix bridge script path', async () => {
    const fetchMock = stubBridgeFetch();

    render(
      <WorkspaceBridgeGuideFloatingPanel
        open
        workspaceId="ws_test"
        apiUrl="http://api.test"
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });
    expect(screen.getByText('./scripts/start_cli_bridge.sh --all')).toBeInTheDocument();
    expect(screen.getByText('./scripts/start_cli_bridge.sh --workspace-id ws_test')).toBeInTheDocument();
  });

  it('checks LaunchAgent status and starts the bridge from the panel', async () => {
    const fetchMock = stubBridgeFetch({ state: 'stopped', running: false });
    const onBridgeServiceChanged = vi.fn();

    render(
      <WorkspaceBridgeGuideFloatingPanel
        open
        workspaceId="ws_test"
        apiUrl="http://api.test"
        onBridgeServiceChanged={onBridgeServiceChanged}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        'http://api.test/api/v1/workspaces/ws_test/agents/bridge-service',
        { cache: 'no-store' },
      );
    });

    fireEvent.click(screen.getByRole('button', { name: 'Start Bridge' }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        'http://api.test/api/v1/workspaces/ws_test/agents/bridge-service/start',
        { method: 'POST', cache: 'no-store' },
      );
    });
    expect(onBridgeServiceChanged).toHaveBeenCalled();
  });

  it('closes from the floating panel header', async () => {
    const onClose = vi.fn();
    const fetchMock = stubBridgeFetch();

    render(
      <WorkspaceBridgeGuideFloatingPanel
        open
        workspaceId="ws_test"
        apiUrl="http://api.test"
        onClose={onClose}
      />,
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Close CLI Bridge Guide' }));

    expect(onClose).toHaveBeenCalled();
  });
});
