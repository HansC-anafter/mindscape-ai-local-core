import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { WorkspaceToolDefinition } from '@/lib/workspace-tools/workspace-tool-registry';
import { CapabilityWorkbenchShell } from './CapabilityWorkbenchShell';

vi.mock('@/lib/capability-ui-loader', async () => {
  const ReactModule = await import('react');
  return {
    primeCapabilityUIComponentMetadata: vi.fn(),
    loadCapabilityUIComponent: vi.fn(async () => function LoadedPanel() {
      return ReactModule.createElement('div', { 'data-testid': 'loaded-panel' }, 'Loaded panel');
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

describe('CapabilityWorkbenchShell', () => {
  beforeEach(() => {
    window.__MindscapePackScopeToolContributions = { ig: [feedLoadTool] };
  });

  it('renders navigation, local-core left rail, and pack tools from the global bridge', () => {
    render(
      <CapabilityWorkbenchShell
        workspaceId="ws_test"
        capabilityCode="ig"
        apiUrl="http://api.test"
        aolHost={{ onSelectObject: vi.fn() }}
        navigation={<aside data-testid="pack-navigation">Navigation</aside>}
      >
        <main data-testid="pack-main">Main</main>
      </CapabilityWorkbenchShell>,
    );

    expect(screen.getByTestId('capability-workbench-shell')).toBeInTheDocument();
    expect(screen.getByTestId('pack-navigation')).toBeInTheDocument();
    expect(screen.getByTestId('pack-main')).toBeInTheDocument();
    expect(screen.getByTestId('pack-scope-tool-ig:feed_grid_card_load_limit')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('pack-scope-navigation-toggle'));
    expect(screen.queryByTestId('pack-navigation')).not.toBeInTheDocument();
  });

  it('temporarily opens collapsed navigation on rail toggle hover', () => {
    render(
      <CapabilityWorkbenchShell
        workspaceId="ws_test"
        capabilityCode="ig"
        apiUrl="http://api.test"
        navigation={<aside data-testid="pack-navigation">Navigation</aside>}
      >
        <main data-testid="pack-main">Main</main>
      </CapabilityWorkbenchShell>,
    );

    fireEvent.click(screen.getByTestId('pack-scope-navigation-toggle'));
    expect(screen.queryByTestId('pack-navigation')).not.toBeInTheDocument();

    fireEvent.mouseEnter(screen.getByTestId('pack-scope-navigation-toggle'));
    expect(screen.getByTestId('pack-navigation')).toBeInTheDocument();

    fireEvent.mouseLeave(screen.getByTestId('capability-workbench-navigation-region'));
    expect(screen.queryByTestId('pack-navigation')).not.toBeInTheDocument();
  });
});
