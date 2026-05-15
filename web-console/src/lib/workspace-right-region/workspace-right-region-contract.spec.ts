import { describe, expect, it } from 'vitest';

import {
  WORKSPACE_RIGHT_REGION_PANEL_WIDTH_PX,
  createCoreRightRailContribution,
  normalizeSettingsPanelContribution,
  normalizeWorkspaceToolContributions,
} from './workspace-right-region-contract';
import type { WorkspaceToolDefinition } from '@/lib/workspace-tools/workspace-tool-registry';

const igRunsTool: WorkspaceToolDefinition = {
  tool_key: 'ig:runs_panel',
  capability_code: 'ig',
  id: 'runs_panel',
  group: 'capability',
  label: 'Runs',
  icon: 'Activity',
  order: 10,
  panel_component_code: 'IGRunsWorkspaceToolPanel',
  panel_component: {
    code: 'IGRunsWorkspaceToolPanel',
    path: 'ui/IGRunsWorkspaceToolPanel.tsx',
    description: 'Runs panel',
    export: 'default',
    artifact_types: [],
    playbook_codes: [],
    import_path: '@/app/capabilities/ig/components/IGRunsWorkspaceToolPanel',
    layout_hint: 'default',
  },
};

describe('workspace right-region contract', () => {
  it('normalizes Local-Core built-ins with fixed right-region defaults', () => {
    const contribution = createCoreRightRailContribution({
      id: 'settings',
      label: 'Settings',
      icon: 'Settings',
      order: 20,
      group: 'workspace',
      testId: 'workspace-settings-tool',
    });

    expect(contribution).toMatchObject({
      contract_version: 'workspace-right-region/v1',
      key: 'core:settings',
      owner_kind: 'core',
      source: 'core.builtin',
      contribution_point: 'workspace.right_rail.tool',
      activation: {
        trigger: 'on_user_open',
        preload: false,
        mount_policy: 'mount_only_while_active',
      },
      lifecycle: {
        hidden_frontend_polling: 'forbidden',
        close_action: 'unmount_panel_only',
        backend_job_policy: 'do_not_stop_without_explicit_user_action',
      },
    });
    expect(contribution.placement.panel_width_px).toBe(WORKSPACE_RIGHT_REGION_PANEL_WIDTH_PX);
    expect(contribution.placement.scroll_policy).toBe('panel_body_y_auto');
  });

  it('filters reserved pack ids from rail tools while preserving the core Runs exception path', () => {
    expect(normalizeWorkspaceToolContributions([igRunsTool])).toEqual([]);
  });

  it('normalizes pack rail tools without allowing layout or activation overrides', () => {
    const [contribution] = normalizeWorkspaceToolContributions([
      {
        ...igRunsTool,
        tool_key: 'ig:inspector',
        id: 'inspector',
        label: 'Inspector',
        order: 30,
      },
    ]);

    expect(contribution).toMatchObject({
      key: 'ig:inspector',
      owner_kind: 'capability',
      owner_code: 'ig',
      source: 'manifest.workspace_tools',
      contribution_point: 'workspace.right_rail.tool',
      group: 'capability',
      placement: {
        panel_width_px: 320,
        scroll_policy: 'panel_body_y_auto',
      },
      activation: {
        preload: false,
      },
    });
  });

  it('normalizes settings panels as settings-panel contributions, not rail tools', () => {
    const contribution = normalizeSettingsPanelContribution({
      capability_code: 'blender_bridge',
      component_code: 'BlenderBridge3DMeshRuntimeSettingsPanel',
      section: 'runtime-environments',
      title: 'Mindscape AI Cloud 3D Mesh',
      order: 60,
      requires_workspace_id: false,
      show_when: {
        runtime_codes: ['mindscape_ai_cloud_3d_mesh'],
      },
      import_path: '@/app/capabilities/blender_bridge/components/BlenderBridge3DMeshRuntimeSettingsPanel',
      export: 'default',
    });

    expect(contribution).toMatchObject({
      key: 'blender_bridge:settings:runtime-environments:BlenderBridge3DMeshRuntimeSettingsPanel',
      source: 'manifest.ui_components.settings',
      contribution_point: 'workspace.settings.panel',
      group: 'tool_runtime',
      placement: {
        panel_width_px: 320,
        scroll_policy: 'panel_body_y_auto',
      },
      component: {
        path: 'ui/components/BlenderBridge3DMeshRuntimeSettingsPanel.tsx',
        provided_props: ['apiUrl'],
      },
    });
  });
});
