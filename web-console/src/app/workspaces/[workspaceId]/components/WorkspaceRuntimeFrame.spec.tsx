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

vi.mock('@/components/brand/BrandNavigation', () => ({
  default: ({ workspaceId }: { workspaceId: string }) => (
    <aside data-testid="brand-navigation">{workspaceId}</aside>
  ),
}));

describe('WorkspaceRuntimeFrame', () => {
  it('lets the AOL runtime shell own right rail spacing for workspace pages', async () => {
    render(
      <WorkspaceRuntimeFrame workspaceId="ws_test">
        <section data-testid="workspace-page">Workspace page</section>
      </WorkspaceRuntimeFrame>,
    );

    expect(screen.getByTestId('aol-shell-content-region')).toBeInTheDocument();
    expect(screen.getByTestId('aol-shell-region')).toBeInTheDocument();
    expect(screen.getByRole('main')).not.toHaveClass('pr-10');
    expect(screen.getByTestId('workspace-page')).toBeInTheDocument();
  });
});
