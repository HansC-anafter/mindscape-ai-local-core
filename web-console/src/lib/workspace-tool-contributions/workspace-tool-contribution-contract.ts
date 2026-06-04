import type {
  WorkspaceToolDefinition,
  WorkspaceToolSlot,
} from '@/lib/workspace-tools/workspace-tool-registry';

export const WORKSPACE_TOOL_RIGHT_RAIL_SLOT: WorkspaceToolSlot = 'workspace.right_rail.tool';
export const WORKBENCH_LEFT_TOOL_RAIL_SLOT: WorkspaceToolSlot = 'workbench.left_tool_rail';

export function getWorkspaceToolSlot(tool: WorkspaceToolDefinition): WorkspaceToolSlot {
  return tool.slot || WORKSPACE_TOOL_RIGHT_RAIL_SLOT;
}

export function filterWorkspaceToolsBySlot(
  tools: WorkspaceToolDefinition[],
  slot: WorkspaceToolSlot,
): WorkspaceToolDefinition[] {
  return tools
    .filter((tool) => getWorkspaceToolSlot(tool) === slot)
    .sort((left, right) => left.order - right.order || left.tool_key.localeCompare(right.tool_key));
}

export function isPackRightRailTool(tool: WorkspaceToolDefinition): boolean {
  return getWorkspaceToolSlot(tool) === WORKSPACE_TOOL_RIGHT_RAIL_SLOT;
}

export function isPackLeftToolRailTool(tool: WorkspaceToolDefinition): boolean {
  return getWorkspaceToolSlot(tool) === WORKBENCH_LEFT_TOOL_RAIL_SLOT;
}
