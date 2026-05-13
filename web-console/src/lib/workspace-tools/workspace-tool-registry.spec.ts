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
});
