import { describe, expect, it } from 'vitest';

import type { WorkspaceToolDefinition } from '@/lib/workspace-tools/workspace-tool-registry';
import {
  AOL_RUNTIME_COMMAND_SURFACE_SLOT,
  WORKBENCH_LEFT_TOOL_RAIL_SLOT,
  WORKSPACE_TOOL_RIGHT_RAIL_SLOT,
  filterWorkspaceToolsBySlot,
  isAOLRuntimeCommandSurfaceTool,
  isPackLeftToolRailTool,
  isPackRightRailTool,
} from './workspace-tool-contribution-contract';

const baseTool: WorkspaceToolDefinition = {
  tool_key: 'ig:runs_panel',
  capability_code: 'ig',
  id: 'runs_panel',
  group: 'capability',
  slot: WORKSPACE_TOOL_RIGHT_RAIL_SLOT,
  label: 'Runs',
  icon: 'Activity',
  order: 20,
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

describe('workspace tool contribution contract', () => {
  it('splits manifest workspace tools by local-core slot', () => {
    const leftTool: WorkspaceToolDefinition = {
      ...baseTool,
      tool_key: 'ig:feed_grid_card_load_limit',
      id: 'feed_grid_card_load_limit',
      slot: WORKBENCH_LEFT_TOOL_RAIL_SLOT,
      label: 'Feed Load',
      icon: 'SlidersHorizontal',
      order: 10,
    };

    expect(isPackRightRailTool(baseTool)).toBe(true);
    expect(isPackLeftToolRailTool(baseTool)).toBe(false);
    expect(isPackRightRailTool(leftTool)).toBe(false);
    expect(isPackLeftToolRailTool(leftTool)).toBe(true);
    expect(filterWorkspaceToolsBySlot([baseTool, leftTool], WORKBENCH_LEFT_TOOL_RAIL_SLOT)).toEqual([leftTool]);
    expect(filterWorkspaceToolsBySlot([baseTool, leftTool], WORKSPACE_TOOL_RIGHT_RAIL_SLOT)).toEqual([baseTool]);
  });

  it('keeps AOL runtime command surface tools out of rail slots', () => {
    const commandSurfaceTool: WorkspaceToolDefinition = {
      ...baseTool,
      tool_key: 'ig:model_lane_commands',
      id: 'model_lane_commands',
      slot: AOL_RUNTIME_COMMAND_SURFACE_SLOT,
      label: 'Model Lanes',
      panel_component_code: 'IGModelLaneCommandPanel',
      panel_component: {
        ...baseTool.panel_component,
        code: 'IGModelLaneCommandPanel',
        path: 'ui/modelLaneCommands/IGModelLaneCommandPanel.tsx',
      },
    };

    expect(isAOLRuntimeCommandSurfaceTool(commandSurfaceTool)).toBe(true);
    expect(isPackRightRailTool(commandSurfaceTool)).toBe(false);
    expect(isPackLeftToolRailTool(commandSurfaceTool)).toBe(false);
    expect(filterWorkspaceToolsBySlot([baseTool, commandSurfaceTool], AOL_RUNTIME_COMMAND_SURFACE_SLOT)).toEqual([
      commandSurfaceTool,
    ]);
  });
});
