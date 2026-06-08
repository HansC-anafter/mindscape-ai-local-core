import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  loadCapabilityUIComponent,
  primeCapabilityUIComponentMetadata,
} from '@/lib/capability-ui-loader';
import { KeyboardShortcutProvider } from '@/lib/keyboard-shortcuts';
import { useKeyboardShortcuts } from '@/lib/keyboard-shortcuts';
import type {
  AddressableObjectHostBridge,
  AddressableSelectionTarget,
} from '@/lib/addressable-object-layer';
import type { KeyboardShortcutProfile } from '@/lib/keyboard-shortcuts';
import type { WorkspaceToolDefinition } from '@/lib/workspace-tools/workspace-tool-registry';
import { PackScopeToolRailHost } from './PackScopeToolRailHost';

vi.mock('@/lib/capability-ui-loader', async () => {
  const ReactModule = await import('react');
  return {
    primeCapabilityUIComponentMetadata: vi.fn(),
    loadCapabilityUIComponent: vi.fn(async () => function LoadedPackToolPanel({
      workspaceId,
      apiUrl,
      tool,
      panelCollapsed,
    }: {
      workspaceId: string;
      apiUrl: string;
      tool: WorkspaceToolDefinition;
      panelCollapsed?: boolean;
    }) {
      return ReactModule.createElement(
        'div',
        {
          'data-testid': 'loaded-pack-tool-panel',
          'data-panel-collapsed': String(Boolean(panelCollapsed)),
          'data-tool-shortcut': tool.shortcut || '',
        },
        `${tool.id}:${workspaceId}:${apiUrl}`,
      );
    }),
  };
});

const feedLoadTool: WorkspaceToolDefinition = {
  tool_key: 'ig:feed_grid_card_load_limit',
  capability_code: 'ig',
  id: 'feed_grid_card_load_limit',
  group: 'capability',
  slot: 'workbench.left_tool_rail',
  label: 'Feed Load',
  icon: 'SlidersHorizontal',
  order: 10,
  shortcut: 'F9',
  panel_component_code: 'FeedGridLoadToolPanel',
  runtime_tool_code: 'ig_query_references',
  aol: {
    object_kind: 'tool',
    object_uri: 'mindscape://ig/tool/feed_grid_card_load_limit',
    role: 'constraint',
  },
  state_schema: {
    load_limit: {
      type: 'integer',
      min: 1,
      max: 300,
    },
  },
  panel_component: {
    code: 'FeedGridLoadToolPanel',
    path: 'ui/workbench/feedGridTool/FeedGridLoadToolPanel.tsx',
    description: 'Feed load panel',
    export: 'FeedGridLoadToolPanel',
    artifact_types: [],
    playbook_codes: [],
    import_path: '@/app/capabilities/ig/components/workbench/feedGridTool/FeedGridLoadToolPanel',
    layout_hint: 'default',
  },
};

function createAolHost(
  onSelectObject: AddressableObjectHostBridge['onSelectObject'],
): AddressableObjectHostBridge {
  return {
    mode: 'idle',
    selection: null,
    currentMeetingId: null,
    requestObjectTargeting: vi.fn(),
    cancelObjectTargeting: vi.fn(),
    onSelectObject,
    clearCurrentObject: vi.fn(),
    openCurrentMeeting: vi.fn(),
  };
}

function ShortcutProfileController({
  onReady,
}: {
  onReady: (setProfile: (profile: KeyboardShortcutProfile) => void) => void;
}) {
  const { setProfile } = useKeyboardShortcuts();
  React.useEffect(() => {
    onReady(setProfile);
  }, [onReady, setProfile]);
  return null;
}

describe('PackScopeToolRailHost', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it('loads a manifest panel lazily without entering AOL object selection', async () => {
    const onSelectObject = vi.fn((selection: AddressableSelectionTarget) => {
      void selection;
    });
    const onNavigationCollapsedChange = vi.fn();

    render(
      <KeyboardShortcutProvider loadProfileOnMount={false}>
        <PackScopeToolRailHost
          workspaceId="ws_test"
          capabilityCode="ig"
          apiUrl="http://api.test"
          tools={[feedLoadTool]}
          navigationCollapsed={false}
          aolHost={createAolHost(onSelectObject)}
          onNavigationCollapsedChange={onNavigationCollapsedChange}
        />
      </KeyboardShortcutProvider>,
    );

    expect(screen.getByTestId('pack-scope-tool-rail')).toBeInTheDocument();
    expect(loadCapabilityUIComponent).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('pack-scope-tool-ig:feed_grid_card_load_limit'));

    expect(onSelectObject).not.toHaveBeenCalled();
    expect(primeCapabilityUIComponentMetadata).toHaveBeenCalledWith('ig', [feedLoadTool.panel_component]);
    await waitFor(() => {
      expect(loadCapabilityUIComponent).toHaveBeenCalledWith(
        'ig',
        'FeedGridLoadToolPanel',
        'http://api.test',
      );
      expect(screen.getByTestId('loaded-pack-tool-panel')).toHaveTextContent(
        'feed_grid_card_load_limit:ws_test:http://api.test',
      );
      expect(screen.getByTestId('loaded-pack-tool-panel')).toHaveAttribute('data-panel-collapsed', 'true');
    });

    fireEvent.click(screen.getByTestId('pack-scope-navigation-toggle'));
    expect(onNavigationCollapsedChange).toHaveBeenCalledWith(true);
  });

  it('opens the panel from the manifest shortcut without hitting editable targets', async () => {
    const onSelectObject = vi.fn((selection: AddressableSelectionTarget) => {
      void selection;
    });

    render(
      <KeyboardShortcutProvider loadProfileOnMount={false}>
        <input data-testid="shortcut-input" />
        <PackScopeToolRailHost
          workspaceId="ws_test"
          capabilityCode="ig"
          apiUrl="http://api.test"
          tools={[feedLoadTool]}
          navigationCollapsed
          aolHost={createAolHost(onSelectObject)}
          onNavigationCollapsedChange={vi.fn()}
        />
      </KeyboardShortcutProvider>,
    );

    fireEvent.keyDown(screen.getByTestId('shortcut-input'), { key: 'F9' });
    expect(loadCapabilityUIComponent).not.toHaveBeenCalled();

    fireEvent.keyDown(window, { key: 'F9' });

    await waitFor(() => {
      expect(screen.getByTestId('loaded-pack-tool-panel')).toBeInTheDocument();
    });
    expect(onSelectObject).not.toHaveBeenCalled();

    fireEvent.keyDown(window, { key: 'F9' });
    await waitFor(() => {
      expect(screen.queryByTestId('loaded-pack-tool-panel')).not.toBeInTheDocument();
    });
  });

  it('uses saved profile overrides for display and dispatch without reloading tools', async () => {
    let applyProfile: (profile: KeyboardShortcutProfile) => void = () => undefined;
    const onReady = vi.fn((setProfile: (profile: KeyboardShortcutProfile) => void) => {
      applyProfile = setProfile;
    });

    render(
      <KeyboardShortcutProvider loadProfileOnMount={false}>
        <ShortcutProfileController onReady={onReady} />
        <PackScopeToolRailHost
          workspaceId="ws_test"
          capabilityCode="ig"
          apiUrl="http://api.test"
          tools={[feedLoadTool]}
          navigationCollapsed
          aolHost={createAolHost(vi.fn())}
          onNavigationCollapsedChange={vi.fn()}
        />
      </KeyboardShortcutProvider>,
    );

    const toolButton = screen.getByTestId('pack-scope-tool-ig:feed_grid_card_load_limit');
    expect(toolButton).toHaveAttribute('title', 'Feed Load (F9)');

    applyProfile({
      schema_version: 1,
      bindings: [
        {
          binding_id: 'workspace_tool:ig:feed_grid_card_load_limit:open',
          command_id: 'pack.workspace_tool.open',
          owner_type: 'pack',
          owner_id: 'ig',
          shortcut: 'F',
          disabled: false,
        },
      ],
    });

    await waitFor(() => {
      expect(toolButton).toHaveAttribute('title', 'Feed Load (F)');
    });

    fireEvent.keyDown(window, { key: 'F9' });
    expect(loadCapabilityUIComponent).not.toHaveBeenCalled();

    fireEvent.keyDown(window, { key: 'F' });
    await waitFor(() => {
      expect(screen.getByTestId('loaded-pack-tool-panel')).toBeInTheDocument();
      expect(screen.getByTestId('loaded-pack-tool-panel')).toHaveAttribute('data-tool-shortcut', 'F');
    });

    fireEvent.keyDown(window, { key: 'F' });
    await waitFor(() => {
      expect(screen.queryByTestId('loaded-pack-tool-panel')).not.toBeInTheDocument();
    });
  });
});
