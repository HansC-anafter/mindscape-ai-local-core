import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { WorkspaceRuntimeProfileFloatingPanel } from './WorkspaceRuntimeProfileFloatingPanel';

vi.mock('@/app/workspaces/[workspaceId]/components/RuntimeProfilePanel', () => ({
  default: ({
    workspaceId,
    apiUrl,
  }: {
    workspaceId: string;
    apiUrl: string;
  }) => (
    <div
      data-testid="mock-runtime-profile-panel"
      data-workspace-id={workspaceId}
      data-api-url={apiUrl}
    />
  ),
}));

describe('WorkspaceRuntimeProfileFloatingPanel', () => {
  it('renders Runtime Profile inside workspace scope', async () => {
    render(
      <WorkspaceRuntimeProfileFloatingPanel
        open
        workspaceId="ws_test"
        apiUrl="http://api.test"
        onClose={vi.fn()}
      />,
    );

    expect(await screen.findByTestId('mock-runtime-profile-panel')).toHaveAttribute('data-workspace-id', 'ws_test');
    expect(screen.getByTestId('mock-runtime-profile-panel')).toHaveAttribute('data-api-url', 'http://api.test');
  });

  it('closes from the floating panel header', () => {
    const onClose = vi.fn();

    render(
      <WorkspaceRuntimeProfileFloatingPanel
        open
        workspaceId="ws_test"
        apiUrl="http://api.test"
        onClose={onClose}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Close Runtime Profile' }));

    expect(onClose).toHaveBeenCalled();
  });
});
