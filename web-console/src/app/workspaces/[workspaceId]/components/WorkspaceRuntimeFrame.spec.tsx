import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import WorkspaceRuntimeFrame from './WorkspaceRuntimeFrame';

vi.mock('@/contexts/WorkspaceDataContext', () => ({
  WorkspaceDataProvider: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="workspace-data-provider">{children}</div>
  ),
}));

vi.mock('@/contexts/ExecutionContextContext', () => ({
  ExecutionContextProvider: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="execution-context-provider">{children}</div>
  ),
}));

describe('WorkspaceRuntimeFrame', () => {
  it('keeps route-level workspace providers without preloading capability runtime chrome', async () => {
    render(
      <WorkspaceRuntimeFrame workspaceId="ws_test">
        <section data-testid="workspace-page">Workspace page</section>
      </WorkspaceRuntimeFrame>,
    );

    expect(screen.getByTestId('workspace-data-provider')).toBeInTheDocument();
    expect(screen.getByTestId('execution-context-provider')).toBeInTheDocument();
    expect(screen.getByRole('main')).not.toHaveClass('pr-10');
    expect(screen.queryByTestId('workspace-surface-shell')).toBeNull();
    expect(screen.queryByTestId('aol-shell-rail')).toBeNull();
    expect(document.querySelector('[data-workspace-tool-rail="true"]')).toBeNull();
    expect(screen.getByTestId('workspace-page')).toBeInTheDocument();
  });
});
