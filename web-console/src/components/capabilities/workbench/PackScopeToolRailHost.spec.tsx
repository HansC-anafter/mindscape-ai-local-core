import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  loadCapabilityUIComponent,
  primeCapabilityUIComponentMetadata,
} from '@/lib/capability-ui-loader';
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

describe('PackScopeToolRailHost', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it('loads a manifest panel lazily without entering AOL object selection', async () => {
    const onSelectObject = vi.fn();
    const onNavigationCollapsedChange = vi.fn();

    render(
      <PackScopeToolRailHost
        workspaceId="ws_test"
        capabilityCode="ig"
        apiUrl="http://api.test"
        tools={[feedLoadTool]}
        navigationCollapsed={false}
        aolHost={{ onSelectObject }}
        onNavigationCollapsedChange={onNavigationCollapsedChange}
      />,
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
    const onSelectObject = vi.fn();

    render(
      <>
        <input data-testid="shortcut-input" />
        <PackScopeToolRailHost
          workspaceId="ws_test"
          capabilityCode="ig"
          apiUrl="http://api.test"
          tools={[feedLoadTool]}
          navigationCollapsed
          aolHost={{ onSelectObject }}
          onNavigationCollapsedChange={vi.fn()}
        />
      </>,
    );

    fireEvent.keyDown(screen.getByTestId('shortcut-input'), { key: 'F9' });
    expect(loadCapabilityUIComponent).not.toHaveBeenCalled();

    fireEvent.keyDown(window, { key: 'F9' });

    await waitFor(() => {
      expect(screen.getByTestId('loaded-pack-tool-panel')).toBeInTheDocument();
    });
    expect(onSelectObject).not.toHaveBeenCalled();
  });
});
