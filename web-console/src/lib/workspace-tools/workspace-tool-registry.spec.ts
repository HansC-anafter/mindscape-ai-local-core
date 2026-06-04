import { describe, expect, it } from 'vitest';

import { normalizeWorkspaceToolDefinitions } from './workspace-tool-registry';

describe('workspace tool registry', () => {
  it('accepts validated pack-provided capability tools and derives stable runtime keys', () => {
    expect(
      normalizeWorkspaceToolDefinitions('ig', [
        {
          id: 'runs_panel',
          group: 'capability',
          label: 'Runs',
          icon: 'Activity',
          order: 20,
          panel_component_code: 'IGRunsWorkspaceToolPanel',
          panel_component: {
            code: 'IGRunsWorkspaceToolPanel',
            path: 'ui/IGRunsWorkspaceToolPanel.tsx',
          },
        },
      ]),
    ).toEqual([
      expect.objectContaining({
        tool_key: 'ig:runs_panel',
        capability_code: 'ig',
        id: 'runs_panel',
        group: 'capability',
        panel_component_code: 'IGRunsWorkspaceToolPanel',
      }),
    ]);
  });

  it('rejects invalid pack tool groups and mismatched panel component references', () => {
    expect(
      normalizeWorkspaceToolDefinitions('ig', [
        {
          id: 'bad_group',
          group: 'execution',
          label: 'Bad',
          panel_component_code: 'IGRunsWorkspaceToolPanel',
          panel_component: { code: 'IGRunsWorkspaceToolPanel' },
        },
        {
          id: 'bad_component',
          group: 'capability',
          label: 'Bad',
          panel_component_code: 'IGRunsWorkspaceToolPanel',
          panel_component: { code: 'OtherPanel' },
        },
      ]),
    ).toEqual([]);
  });

  it('preserves runtime asset metadata for workspace tool panels', () => {
    const tools = normalizeWorkspaceToolDefinitions('ig', [
      {
        id: 'host_resource_lanes',
        group: 'capability',
        label: 'Host Lanes',
        icon: 'Route',
        order: 20,
        panel_component_code: 'IGHostResourceLanesWorkspaceToolPanel',
        panel_component: {
          code: 'IGHostResourceLanesWorkspaceToolPanel',
          path: 'ui/IGHostResourceLanesWorkspaceToolPanel.tsx',
          asset_url: '/api/v1/capability-packs/installed-capabilities/ig/ui-assets/1.0.88/components/IGHostResourceLanesWorkspaceToolPanel.mjs',
          integrity: 'sha256-test',
          runtime: 'mindscape-react-bridge-v1',
          bytes: 16113,
          asset_path: '1.0.88/components/IGHostResourceLanesWorkspaceToolPanel.mjs',
        },
      },
    ]);

    expect(tools[0].panel_component).toEqual(
      expect.objectContaining({
        asset_url: '/api/v1/capability-packs/installed-capabilities/ig/ui-assets/1.0.88/components/IGHostResourceLanesWorkspaceToolPanel.mjs',
        integrity: 'sha256-test',
        runtime: 'mindscape-react-bridge-v1',
        bytes: 16113,
        asset_path: '1.0.88/components/IGHostResourceLanesWorkspaceToolPanel.mjs',
      }),
    );
  });

  it('normalizes slot-aware pack tools with runtime object metadata', () => {
    const tools = normalizeWorkspaceToolDefinitions('ig', [
      {
        id: 'feed_grid_card_load_limit',
        group: 'capability',
        slot: 'workbench.left_tool_rail',
        label: 'Feed Load',
        icon: 'SlidersHorizontal',
        order: 10,
        shortcut: 'B',
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
        },
      },
    ]);

    expect(tools[0]).toMatchObject({
      tool_key: 'ig:feed_grid_card_load_limit',
      slot: 'workbench.left_tool_rail',
      shortcut: 'B',
      runtime_tool_code: 'ig_query_references',
      aol: {
        object_kind: 'tool',
        object_uri: 'mindscape://ig/tool/feed_grid_card_load_limit',
        role: 'constraint',
      },
    });
    expect(tools[0].state_schema).toEqual(
      expect.objectContaining({
        load_limit: expect.objectContaining({ max: 300 }),
      }),
    );
  });
});
