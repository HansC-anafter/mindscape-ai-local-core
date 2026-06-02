import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { WorkspaceRuntimeCliFloatingPanel } from './WorkspaceRuntimeCliFloatingPanel';

vi.mock('@/app/workspaces/[workspaceId]/components/CliApiKeysSection', () => ({
  default: ({
    workspaceId,
    initialAgentTab,
  }: {
    workspaceId?: string;
    initialAgentTab?: string;
  }) => (
    <div
      data-testid="mock-cli-api-keys-section"
      data-workspace-id={workspaceId || ''}
      data-initial-agent-tab={initialAgentTab || ''}
    />
  ),
}));

describe('WorkspaceRuntimeCliFloatingPanel', () => {
  it('renders Runtime CLI inside workspace scope and defaults to Codex accounts', async () => {
    render(
      <WorkspaceRuntimeCliFloatingPanel
        open
        workspaceId="ws_test"
        onClose={vi.fn()}
      />,
    );

    expect(await screen.findByTestId('mock-cli-api-keys-section')).toHaveAttribute('data-workspace-id', 'ws_test');
    expect(screen.getByTestId('mock-cli-api-keys-section')).toHaveAttribute('data-initial-agent-tab', 'codex');
  });

  it('closes from the floating panel header', () => {
    const onClose = vi.fn();

    render(
      <WorkspaceRuntimeCliFloatingPanel
        open
        workspaceId="ws_test"
        onClose={onClose}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Close Runtime CLI' }));

    expect(onClose).toHaveBeenCalled();
  });
});
