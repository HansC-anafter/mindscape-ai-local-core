import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { WorkspaceToolOverlayFloatingPanel } from './WorkspaceToolOverlayFloatingPanel';

vi.mock('@/app/workspaces/[workspaceId]/components/ToolOverlayPanel', () => ({
  default: ({ workspaceId }: { workspaceId: string }) => (
    <div data-testid="mock-tool-overlay-panel" data-workspace-id={workspaceId} />
  ),
}));

describe('WorkspaceToolOverlayFloatingPanel', () => {
  it('renders Tool Overlay inside workspace scope', async () => {
    render(
      <WorkspaceToolOverlayFloatingPanel
        open
        workspaceId="ws_test"
        onClose={vi.fn()}
      />,
    );

    expect(await screen.findByTestId('mock-tool-overlay-panel')).toHaveAttribute('data-workspace-id', 'ws_test');
  });

  it('closes from the floating panel header', () => {
    const onClose = vi.fn();

    render(
      <WorkspaceToolOverlayFloatingPanel
        open
        workspaceId="ws_test"
        onClose={onClose}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Close Tool Overlay' }));

    expect(onClose).toHaveBeenCalled();
  });
});
