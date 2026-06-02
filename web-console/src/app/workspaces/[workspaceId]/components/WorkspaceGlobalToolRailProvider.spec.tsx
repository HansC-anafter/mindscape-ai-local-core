import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import WorkspaceGlobalToolRailProvider from './WorkspaceGlobalToolRailProvider';
import WorkspaceThreadBundleToolRegistration from './WorkspaceThreadBundleToolRegistration';

const windowOpenMock = vi.hoisted(() => vi.fn(() => ({ opener: null })));

vi.mock('@/contexts/WorkspaceDataContext', () => ({
  useWorkspaceDataOptional: () => ({
    executions: [
      { id: 'exec_running', status: 'running' },
      { id: 'exec_done', status: 'completed' },
    ],
  }),
}));

vi.mock('@/lib/api-url', () => ({
  getApiBaseUrl: () => 'http://api.test',
}));

vi.mock('../capability-ui-hosts/WorkspacePackToolPanel', async () => {
  const ReactModule = await import('react');
  return {
    default: () => ReactModule.createElement('div', { 'data-testid': 'mock-pack-panel' }, 'Pack panel'),
  };
});

vi.mock('../capability-ui-hosts/WorkspaceSettingsToolPanel', async () => {
  const ReactModule = await import('react');
  return {
    default: () => ReactModule.createElement('div', { 'data-testid': 'mock-settings-panel' }, 'Settings panel'),
  };
});

vi.mock('../capability-ui-hosts/WorkspaceRunsPanel', async () => {
  const ReactModule = await import('react');
  return {
    default: () => ReactModule.createElement('div', { 'data-testid': 'mock-runs-panel' }, 'Runs panel'),
  };
});

vi.mock('@/components/workspace/ThreadBundlePanel', async () => {
  const ReactModule = await import('react');
  return {
    ThreadBundlePanel: ({ threadId }: { threadId: string | null }) => ReactModule.createElement(
      'div',
      { 'data-testid': 'mock-thread-bundle-panel' },
      `Bundle ${threadId}`,
    ),
  };
});

describe('WorkspaceGlobalToolRailProvider', () => {
  beforeEach(() => {
    vi.stubGlobal('open', windowOpenMock);
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it('owns the workspace rail and mounts one active panel at a time', async () => {
    render(
      <WorkspaceGlobalToolRailProvider workspaceId="ws_test">
        <section data-testid="workspace-content">Workspace content</section>
      </WorkspaceGlobalToolRailProvider>,
    );

    expect(screen.getByTestId('workspace-content')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-global-tool-rail')).toBeInTheDocument();
    expect(screen.queryByTestId('workspace-global-tool-panel')).toBeNull();
    expect(screen.getByTestId('workspace-runs-tool')).toHaveTextContent('1');

    fireEvent.click(screen.getByTestId('workspace-pack-tool'));
    expect(screen.getByTestId('workspace-global-tool-panel')).toHaveAttribute('data-active-tool-key', 'core:pack');
    await waitFor(() => {
      expect(screen.getByTestId('mock-pack-panel')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('workspace-settings-tool'));
    expect(screen.getByTestId('workspace-global-tool-panel')).toHaveAttribute('data-active-tool-key', 'core:settings');
    await waitFor(() => {
      expect(screen.getByTestId('mock-settings-panel')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('mock-pack-panel')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Close Settings' }));
    expect(screen.queryByTestId('workspace-global-tool-panel')).toBeNull();
  });

  it('routes graph without mounting a panel', () => {
    render(
      <WorkspaceGlobalToolRailProvider workspaceId="ws_graph">
        <section>Workspace content</section>
      </WorkspaceGlobalToolRailProvider>,
    );

    fireEvent.click(screen.getByTestId('workspace-graph-tool'));

    expect(windowOpenMock).toHaveBeenCalledWith(
      '/mindscape/canvas?workspaceId=ws_graph',
      '_blank',
      'noopener,noreferrer',
    );
    expect(screen.queryByTestId('workspace-global-tool-panel')).toBeNull();
  });

  it('registers the bundle tool only when a thread is selected', async () => {
    const { rerender } = render(
      <WorkspaceGlobalToolRailProvider workspaceId="ws_test">
        <WorkspaceThreadBundleToolRegistration
          workspaceId="ws_test"
          apiUrl="http://api.test"
          selectedThreadId={null}
        />
      </WorkspaceGlobalToolRailProvider>,
    );

    expect(screen.queryByTestId('workspace-bundle-tool')).toBeNull();

    rerender(
      <WorkspaceGlobalToolRailProvider workspaceId="ws_test">
        <WorkspaceThreadBundleToolRegistration
          workspaceId="ws_test"
          apiUrl="http://api.test"
          selectedThreadId="thread_1"
        />
      </WorkspaceGlobalToolRailProvider>,
    );

    expect(screen.getByTestId('workspace-bundle-tool')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('workspace-bundle-tool'));

    expect(screen.getByTestId('workspace-global-tool-panel')).toHaveAttribute('data-active-tool-key', 'core:bundle');
    await waitFor(() => {
      expect(screen.getByTestId('mock-thread-bundle-panel')).toHaveTextContent('Bundle thread_1');
    });
  });
});
