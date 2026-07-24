import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import WorkspaceHeaderBar from './WorkspaceHeaderBar';

vi.mock('../../components/DeviceStatusIndicator', () => ({
  DeviceStatusIndicator: () => <span>Device status</span>,
}));

vi.mock('../../../../components/execution/TrainHeader', () => ({
  default: () => <div data-testid="train-header">Train header</div>,
}));

vi.mock('./VisibilityBadge', () => ({
  default: () => <span>Private</span>,
}));

vi.mock('./WorkspaceGroupIndicator', () => ({
  default: () => <span>Workspace group</span>,
}));

vi.mock('@/contexts/WorkspaceGroupContext', () => ({
  useWorkspaceGroup: () => ({
    activeGroup: null,
    activeRole: null,
    groups: [],
    isLoading: false,
    selectGroup: vi.fn(),
  }),
}));

describe('WorkspaceHeaderBar', () => {
  it('reserves the mobile page-top host slot without moving the desktop status position', () => {
    render(
      <WorkspaceHeaderBar
        workspace={{ title: 'Demo workspace' }}
        workspaceId="ws_demo"
        apiUrl="http://localhost:8200"
        executionState={{
          trainSteps: [],
          overallProgress: 0,
          isExecuting: false,
        }}
      />,
    );

    const statusSlot = screen.getByTestId('workspace-header-device-status-slot');
    expect(statusSlot.className).toContain('right-14');
    expect(statusSlot.className).toContain('md:right-4');
    expect(statusSlot).toHaveTextContent('Device status');
  });
});
