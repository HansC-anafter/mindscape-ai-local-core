import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { WorkspaceBridgeGuideFloatingPanel } from './WorkspaceBridgeGuideFloatingPanel';

describe('WorkspaceBridgeGuideFloatingPanel', () => {
  it('renders bridge commands from the workspace agents response path', () => {
    render(
      <WorkspaceBridgeGuideFloatingPanel
        open
        workspaceId="ws_test"
        bridgeScriptPath="/project/scripts/start_cli_bridge.sh"
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByRole('dialog', { name: 'Workspace CLI Bridge' })).toBeInTheDocument();
    expect(screen.getByText('/project/scripts/start_cli_bridge.sh --all')).toBeInTheDocument();
    expect(screen.getByText('/project/scripts/start_cli_bridge.sh --workspace-id ws_test')).toBeInTheDocument();
    expect(screen.getByText((text) => text.includes('start_cli_bridge.ps1 -All'))).toBeInTheDocument();
    expect(screen.getByText((text) => text.includes('start_cli_bridge.ps1 -WorkspaceId ws_test'))).toBeInTheDocument();
  });

  it('falls back to the repo-relative Unix bridge script path', () => {
    render(
      <WorkspaceBridgeGuideFloatingPanel
        open
        workspaceId="ws_test"
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText('./scripts/start_cli_bridge.sh --all')).toBeInTheDocument();
    expect(screen.getByText('./scripts/start_cli_bridge.sh --workspace-id ws_test')).toBeInTheDocument();
  });

  it('closes from the floating panel header', () => {
    const onClose = vi.fn();

    render(
      <WorkspaceBridgeGuideFloatingPanel
        open
        workspaceId="ws_test"
        onClose={onClose}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Close CLI Bridge Guide' }));

    expect(onClose).toHaveBeenCalled();
  });
});
