import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import './WorkspaceSurfaceShell.test-support';
import { KeyboardShortcutProvider } from '@/lib/keyboard-shortcuts';
import { fetchWorkspaceToolDefinitions } from '@/lib/workspace-tools/workspace-tool-registry';
import {
  ActionableWorkbenchMetadataRegistration,
  WorkbenchMetadataRegistration,
} from './WorkspaceSurfaceShell.test-support';
import WorkspaceSurfaceShell from './WorkspaceSurfaceShell';

describe('WorkspaceSurfaceShell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchWorkspaceToolDefinitions).mockResolvedValue([]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('composes workspace providers with the generic rail for canonical capability hosts', async () => {
    render(
      <WorkspaceSurfaceShell
        workspaceId="ws_test"
        activeCapabilityCode="demo_capability"
        surfacePath={['sessions', 'session_route_001']}
      >
        <div data-testid="surface-content">Capability surface</div>
      </WorkspaceSurfaceShell>,
    );

    expect(screen.getByTestId('workspace-data-provider')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-data-provider')).toHaveAttribute(
      'data-initial-load-profile',
      'capability-host',
    );
    expect(screen.getByTestId('execution-context-provider')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-surface-shell')).toHaveAttribute(
      'data-active-capability-code',
      'demo_capability',
    );
    expect(screen.getByTestId('workspace-surface-shell')).toHaveAttribute(
      'data-surface-path',
      'sessions/session_route_001',
    );
    expect(screen.getByTestId('surface-content')).toBeInTheDocument();
    expect(screen.getByTestId('capability-host-rail-slot')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-global-tool-rail')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-global-tool-rail')).toHaveAttribute(
      'data-workspace-tool-rail-placement',
      'side',
    );
    expect(screen.getByTestId('workspace-runs-tool')).toHaveTextContent('1');
    expect(document.querySelector('[data-workspace-tool-rail="true"]')).not.toBeNull();
    await waitFor(() => {
      expect(screen.queryByTestId('workspace-info-tool')).not.toBeInTheDocument();
    });
    expect(screen.getByTestId('workspace-settings-tool')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-pack-tool')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-motion-source-tool')).toBeInTheDocument();
    expect(screen.getByTestId('aol-global-anchor')).toBeInTheDocument();
    expect(screen.getByTestId('aol-runtime-flow-anchor')).toBeInTheDocument();
    expect(screen.getByTestId('aol-workspace-region')).toHaveAttribute(
      'data-aol-panel-loaded',
      'idle',
    );
    expect(screen.queryByTestId('workspace-global-tool-panel')).not.toBeInTheDocument();
  });

  it('keeps manifest shortcuts on workspace right-rail tools', async () => {
    vi.mocked(fetchWorkspaceToolDefinitions).mockResolvedValue([
      {
        tool_key: 'shortcut_capability:inspector',
        capability_code: 'shortcut_capability',
        id: 'inspector',
        group: 'capability',
        slot: 'workspace.right_rail.tool',
        label: 'Inspector',
        icon: 'PanelRight',
        order: 30,
        shortcut: 'E',
        panel_component_code: 'IGInspectorWorkspaceToolPanel',
        panel_component: {
          code: 'IGInspectorWorkspaceToolPanel',
          path: 'ui/IGInspectorWorkspaceToolPanel.tsx',
          description: 'Inspector panel',
          export: 'default',
          artifact_types: [],
          playbook_codes: [],
          import_path: '@/app/capabilities/ig/components/IGInspectorWorkspaceToolPanel',
          layout_hint: 'default',
        },
      },
    ]);

    render(
      <WorkspaceSurfaceShell
        workspaceId="ws_shortcut_capability"
        activeCapabilityCode="shortcut_capability"
        surfacePath={[]}
      >
        <div data-testid="surface-content">IG workbench</div>
      </WorkspaceSurfaceShell>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('workspace-tool-shortcut_capability:inspector')).toHaveAttribute('title', 'Inspector (E)');
      expect(screen.getByTestId('workspace-tool-shortcut_capability:inspector')).toHaveAttribute('aria-keyshortcuts', 'E');
    }, { timeout: 4000 });
  });

  it('toggles AOL object selection from the runtime rail shortcut', async () => {
    render(
      <KeyboardShortcutProvider loadProfileOnMount={false}>
        <WorkspaceSurfaceShell
          workspaceId="ws_test"
          activeCapabilityCode="demo_capability"
          surfacePath={[]}
        >
          <input data-testid="aol-shortcut-input" />
        </WorkspaceSurfaceShell>
      </KeyboardShortcutProvider>,
    );

    fireEvent.keyDown(screen.getByTestId('aol-shortcut-input'), { key: 'b' });
    expect(screen.getByTestId('aol-workspace-region')).toHaveAttribute('data-aol-mode', 'idle');

    fireEvent.keyDown(window, { key: 'b' });
    await waitFor(() => {
      expect(screen.getByTestId('aol-workspace-region')).toHaveAttribute('data-aol-mode', 'selecting');
    });

    fireEvent.keyDown(window, { key: 'b' });
    await waitFor(() => {
      expect(screen.getByTestId('aol-workspace-region')).toHaveAttribute('data-aol-mode', 'idle');
    });
  });

  it('does not reserve the Info rail for metadata-only workbench references', async () => {
    render(
      <WorkspaceSurfaceShell
        workspaceId="ws_test"
        activeCapabilityCode="demo_capability"
        surfacePath={['sessions', 'session_route_001']}
      >
        <WorkbenchMetadataRegistration />
      </WorkspaceSurfaceShell>,
    );

    await waitFor(() => {
      expect(screen.queryByTestId('workspace-info-tool')).not.toBeInTheDocument();
    });
  });

  it('opens the shared workbench info panel for actionable metadata', async () => {
    render(
      <WorkspaceSurfaceShell
        workspaceId="ws_test"
        activeCapabilityCode="demo_capability"
        surfacePath={['sessions', 'session_route_001']}
      >
        <ActionableWorkbenchMetadataRegistration />
      </WorkspaceSurfaceShell>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('workspace-info-tool')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('workspace-info-tool'));

    expect(screen.getByTestId('workspace-global-tool-panel')).toHaveAttribute(
      'data-active-tool-key',
      'workspace-surface:demo_capability:workbench-info',
    );
    expect(screen.getByTestId('capability-workbench-info-panel')).toHaveTextContent('Demo Capability');
    expect(screen.getByText('artifact:asset_test')).toBeInTheDocument();
    expect(screen.getByText('inspect / review / item01')).toBeInTheDocument();
  });

  it('uses the shared host tool tray during mobile placement', async () => {
    vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
      matches: query === '(max-width: 767px)',
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })));

    render(
      <WorkspaceSurfaceShell
        workspaceId="ws_test"
        activeCapabilityCode="demo_capability"
        surfacePath={[]}
      >
        <div data-testid="surface-content">Capability surface</div>
      </WorkspaceSurfaceShell>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('capability-host-tool-shell')).toHaveAttribute(
        'data-workbench-placement',
        'mobile',
      );
    });
    expect(screen.queryByTestId('capability-host-rail-slot')).toBeNull();
    expect(screen.queryByTestId('workspace-global-tool-rail')).toBeNull();
    expect(screen.getByTestId('workspace-mobile-host-rail-controls')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-mobile-host-rail-controls').className).toContain('right-2');
    expect(screen.getByTestId('workspace-mobile-host-rail-controls').className).toContain('top-40');
    expect(screen.getByTestId('workspace-mobile-host-rail-controls').className).not.toContain('top-1/2');
    expect(screen.getByTestId('workspace-mobile-host-rail-controls').className).not.toContain('-translate-y-1/2');
    expect(screen.getByTestId('workspace-global-tool-tray-toggle')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('workspace-global-tool-tray-toggle'));

    expect(screen.getByTestId('workspace-global-tool-rail')).toHaveAttribute(
      'data-workspace-tool-rail-placement',
      'tray',
    );
    expect(screen.getByTestId('workspace-runs-tool')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-settings-tool')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-graph-tool')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-pack-tool')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-motion-source-tool')).toBeInTheDocument();
  });

});
