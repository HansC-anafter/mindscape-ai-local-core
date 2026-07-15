import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  useWorkspaceGroup,
  WorkspaceGroupContextProvider,
} from './WorkspaceGroupContext';


const { getMock } = vi.hoisted(() => ({ getMock: vi.fn() }));

vi.mock('@/api/client', () => ({
  MindscapeAPIClient: {
    fromBaseUrl: () => ({ get: getMock }),
  },
}));

vi.mock('@/lib/api-url', () => ({ getApiBaseUrl: () => 'http://api.test' }));

const groups = [
  {
    id: 'group-a',
    display_name: 'Group A',
    revision: 3,
    role_map: { 'workspace-a': 'dispatch' },
    members: [{ workspace_id: 'workspace-a', role: 'dispatch' }],
    is_ready: false,
  },
  {
    id: 'group-b',
    display_name: 'Group B',
    revision: 1,
    role_map: { 'workspace-b': 'cell' },
    members: [{ workspace_id: 'workspace-b', role: 'cell' }],
    is_ready: false,
  },
];

function Harness() {
  const context = useWorkspaceGroup();
  return (
    <div>
      <span data-testid="groups">{context.groups.length}</span>
      <span data-testid="active">{context.activeGroup?.display_name || 'single'}</span>
      <button type="button" onClick={() => context.selectGroup('group-a')}>select</button>
      <button type="button" onClick={() => context.selectGroup(null)}>clear</button>
    </div>
  );
}

describe('WorkspaceGroupContextProvider', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    getMock.mockReset();
    getMock.mockResolvedValue({
      ok: true,
      json: async () => ({ groups }),
    });
  });

  it('loads once, filters by workspace, and never selects the first group implicitly', async () => {
    render(
      <WorkspaceGroupContextProvider workspaceId="workspace-a">
        <Harness />
      </WorkspaceGroupContextProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('groups')).toHaveTextContent('1'));
    expect(screen.getByTestId('active')).toHaveTextContent('single');
    expect(getMock).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: 'select' }));
    expect(screen.getByTestId('active')).toHaveTextContent('Group A');
    fireEvent.click(screen.getByRole('button', { name: 'clear' }));
    expect(screen.getByTestId('active')).toHaveTextContent('single');
  });

  it('restores only a session selection that contains the current workspace', async () => {
    window.sessionStorage.setItem('mindscape.activeWorkspaceGroupId', 'group-a');
    render(
      <WorkspaceGroupContextProvider workspaceId="workspace-a">
        <Harness />
      </WorkspaceGroupContextProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('active')).toHaveTextContent('Group A'));
  });
});
