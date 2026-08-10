import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { KeyboardShortcutProvider } from '@/lib/keyboard-shortcuts';
import WorkspaceGlobalToolRailProvider from './WorkspaceGlobalToolRailProvider';
import WorkspaceThreadBundleToolRegistration from './WorkspaceThreadBundleToolRegistration';

const windowOpenMock = vi.hoisted(() => vi.fn(() => ({ opener: null })));

vi.mock('@/lib/i18n', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/i18n')>();
  const translator = actual.createTranslator('en');
  return {
    ...actual,
    useT: () => translator,
  };
});
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

vi.mock('@/components/workspace/device-binding/MotionSourceRailPanel', async () => {
  const ReactModule = await import('react');
  return {
    default: () => ReactModule.createElement(
      'div',
      { 'data-testid': 'mock-motion-source-panel' },
      'Motion source panel',
    ),
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
    window.history.replaceState({}, '', '/workspaces/ws_test');
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
    expect(screen.getByTestId('workspace-runs-tool')).toHaveAttribute('title', 'Runs (R)');
    expect(screen.getByTestId('workspace-settings-tool')).toHaveAttribute('title', 'Settings (S)');
    expect(screen.getByTestId('workspace-pack-tool')).toHaveAttribute('title', 'Pack (A)');
    expect(screen.getByTestId('workspace-motion-source-tool')).toHaveAttribute('title', 'Motion Source (C)');
    expect(screen.getByTestId('workspace-graph-tool')).toHaveAttribute('title', 'Graph (G)');
    expect(screen.getByTestId('workspace-global-tool-group-graph')).toContainElement(
      screen.getByTestId('workspace-graph-tool'),
    );
    expect(screen.getByTestId('workspace-global-tool-group-workspace')).not.toContainElement(
      screen.getByTestId('workspace-graph-tool'),
    );
    await waitFor(() => {
      expect(screen.getByTestId('workspace-voice-tool')).toBeEnabled();
      expect(screen.getByTestId('workspace-voice-tool')).toHaveAttribute('title', 'Voice');
      expect(screen.getByTestId('workspace-global-tool-group-runtime')).toContainElement(
        screen.getByTestId('workspace-voice-tool'),
      );
    });

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

  it('toggles core workspace rail tools from left-hand default shortcuts', async () => {
    render(
      <KeyboardShortcutProvider loadProfileOnMount={false}>
        <WorkspaceGlobalToolRailProvider workspaceId="ws_shortcuts">
          <input data-testid="workspace-shortcut-input" />
        </WorkspaceGlobalToolRailProvider>
      </KeyboardShortcutProvider>,
    );

    fireEvent.keyDown(screen.getByTestId('workspace-shortcut-input'), { key: 's' });
    expect(screen.queryByTestId('workspace-global-tool-panel')).toBeNull();

    fireEvent.keyDown(window, { key: 's' });
    await waitFor(() => {
      expect(screen.getByTestId('workspace-global-tool-panel')).toHaveAttribute('data-active-tool-key', 'core:settings');
    });

    fireEvent.keyDown(window, { key: 's' });
    await waitFor(() => {
      expect(screen.queryByTestId('workspace-global-tool-panel')).toBeNull();
    });

    fireEvent.keyDown(window, { key: 'a' });
    await waitFor(() => {
      expect(screen.getByTestId('workspace-global-tool-panel')).toHaveAttribute('data-active-tool-key', 'core:pack');
    });

    fireEvent.keyDown(window, { key: 'c' });
    await waitFor(() => {
      expect(screen.getByTestId('workspace-global-tool-panel')).toHaveAttribute('data-active-tool-key', 'core:motion_source');
    });

    fireEvent.keyDown(window, { key: 'r' });
    await waitFor(() => {
      expect(screen.getByTestId('workspace-global-tool-panel')).toHaveAttribute('data-active-tool-key', 'core:runs_panel');
    });

    fireEvent.keyDown(window, { key: 'g' });
    expect(windowOpenMock).toHaveBeenCalledWith(
      '/mindscape/canvas?workspaceId=ws_shortcuts',
      '_blank',
      'noopener,noreferrer',
    );
    expect(screen.queryByTestId('workspace-global-tool-panel')).toBeNull();
  });

  it('toggles the active workspace tool panel with the tilde shortcut', async () => {
    render(
      <KeyboardShortcutProvider loadProfileOnMount={false}>
        <WorkspaceGlobalToolRailProvider workspaceId="ws_test">
          <input data-testid="workspace-tilde-input" />
        </WorkspaceGlobalToolRailProvider>
      </KeyboardShortcutProvider>,
    );

    fireEvent.click(screen.getByTestId('workspace-pack-tool'));
    await waitFor(() => {
      expect(screen.getByTestId('workspace-global-tool-panel')).toHaveAttribute('data-active-tool-key', 'core:pack');
      expect(screen.getByTestId('mock-pack-panel')).toBeInTheDocument();
    });

    fireEvent.keyDown(screen.getByTestId('workspace-tilde-input'), { key: '`' });
    expect(screen.getByTestId('workspace-global-tool-panel')).toHaveAttribute('data-active-tool-key', 'core:pack');

    fireEvent.keyDown(window, { key: '`', code: 'Backquote' });
    await waitFor(() => {
      expect(screen.queryByTestId('workspace-global-tool-panel')).toBeNull();
    });

    fireEvent.keyDown(window, { key: '~', code: 'Backquote', shiftKey: true });
    await waitFor(() => {
      expect(screen.getByTestId('workspace-global-tool-panel')).toHaveAttribute('data-active-tool-key', 'core:pack');
    });
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

  it('opens the motion source panel from the runtime rail', async () => {
    render(
      <WorkspaceGlobalToolRailProvider workspaceId="ws_motion">
        <section>Workspace content</section>
      </WorkspaceGlobalToolRailProvider>,
    );

    fireEvent.click(screen.getByTestId('workspace-motion-source-tool'));

    expect(screen.getByTestId('workspace-global-tool-panel')).toHaveAttribute('data-active-tool-key', 'core:motion_source');
    await waitFor(() => {
      expect(screen.getByTestId('mock-motion-source-panel')).toBeInTheDocument();
    });
  });

  it('opens the motion source panel from a workspace tool deep link', async () => {
    window.history.replaceState({}, '', '/workspaces/ws_motion?tool=motion_source');

    render(
      <WorkspaceGlobalToolRailProvider workspaceId="ws_motion">
        <section>Workspace content</section>
      </WorkspaceGlobalToolRailProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('workspace-global-tool-panel')).toHaveAttribute('data-active-tool-key', 'core:motion_source');
    });
    expect(screen.getByTestId('mock-motion-source-panel')).toBeInTheDocument();
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

  it('uses the shared right-side host tray on mobile workbench frames', async () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({
      matches: true,
      media: '(max-width: 767px)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })));

    render(
      <WorkspaceGlobalToolRailProvider workspaceId="ws_mobile">
        <section>Workspace content</section>
      </WorkspaceGlobalToolRailProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('workspace-global-tool-shell')).toHaveAttribute('data-workbench-placement', 'mobile');
      expect(screen.getByTestId('workspace-mobile-host-rail-controls')).toBeInTheDocument();
      expect(screen.getByTestId('workspace-mobile-host-rail-controls').className).toContain('right-2');
      expect(screen.getByTestId('workspace-mobile-host-rail-controls').className).toContain(
        'top-[calc(0.5rem+env(safe-area-inset-top,0px))]',
      );
      expect(screen.getByTestId('workspace-mobile-host-rail-controls').className).not.toContain('top-40');
      expect(screen.getByTestId('workspace-mobile-host-rail-controls').className).not.toContain('top-1/2');
      expect(screen.getByTestId('workspace-mobile-host-rail-controls').className).not.toContain('-translate-y-1/2');
      expect(screen.queryByTestId('workspace-global-tool-rail')).toBeNull();
      expect(screen.getByTestId('workspace-global-tool-tray-toggle')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('workspace-global-tool-tray-toggle'));
    expect(screen.getByTestId('workspace-global-tool-rail')).toHaveAttribute('data-workspace-tool-rail-placement', 'tray');

    fireEvent.click(screen.getByTestId('workspace-settings-tool'));

    expect(screen.getByTestId('workspace-global-tool-panel')).toHaveAttribute('data-workbench-placement', 'mobile');
    expect(screen.getByTestId('workspace-global-tool-panel').className).toContain('right-14');
    expect(screen.getByTestId('workspace-global-tool-panel').className).toContain('bottom-[');
    expect(screen.getByTestId('workspace-global-tool-panel').className).toContain('max-h-none');
    await waitFor(() => {
      expect(screen.getByTestId('mock-settings-panel')).toBeInTheDocument();
    });
  });
});
