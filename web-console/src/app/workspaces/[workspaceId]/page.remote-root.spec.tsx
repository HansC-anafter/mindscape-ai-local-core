import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

let ingressMarker: string | null = null;

vi.mock('next/headers', () => ({
  headers: () => ({
    get: (name: string) => (
      name === 'x-mindscape-remote-ingress' ? ingressMarker : null
    ),
  }),
}));

vi.mock('./RemoteWorkspaceLanding', () => ({
  default: ({ workspaceId }: { workspaceId: string }) => (
    <div data-testid="remote-workspace-landing">Remote {workspaceId}</div>
  ),
}));

vi.mock('./WorkspacePageClientLoader', () => ({
  default: ({ workspaceId }: { workspaceId: string }) => (
    <div data-testid="local-workspace-full-ui">Local {workspaceId}</div>
  ),
}));

import WorkspacePage from './page';

describe('workspace root trusted ingress seam', () => {
  beforeEach(() => {
    ingressMarker = null;
  });

  it('mounts only the bounded landing for the trusted remote marker', async () => {
    ingressMarker = 'remote_workbench';
    render(await WorkspacePage({ params: { workspaceId: 'workspace-a' } }));

    expect(screen.getByTestId('remote-workspace-landing')).toBeInTheDocument();
    expect(screen.queryByTestId('local-workspace-full-ui')).not.toBeInTheDocument();
  });

  it.each([null, 'client-spoof', 'remote_workbench '])(
    'keeps the existing full local UI for marker %s',
    async (marker) => {
      ingressMarker = marker;
      render(await WorkspacePage({ params: { workspaceId: 'workspace-a' } }));

      expect(screen.getByTestId('local-workspace-full-ui')).toBeInTheDocument();
      expect(screen.queryByTestId('remote-workspace-landing')).not.toBeInTheDocument();
    },
  );
});
