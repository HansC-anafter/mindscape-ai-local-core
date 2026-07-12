export type WorkspaceToolGroup = 'workspace' | 'execution' | 'meeting' | 'capability';
export type WorkspaceToolSlot =
  | 'workspace.right_rail.tool'
  | 'workbench.left_tool_rail'
  | 'aol.runtime.command_surface';

export interface WorkspaceToolAOLDefinition {
  object_kind: string;
  object_uri: string;
  role: string;
}

export interface WorkspaceToolPanelComponent {
  code: string;
  path: string;
  description: string;
  export: string;
  artifact_types: string[];
  playbook_codes: string[];
  import_path: string;
  layout_hint: 'default' | 'scrollable_full_bleed';
  asset_url?: string;
  integrity?: string;
  runtime?: string;
  bytes?: number;
  asset_path?: string;
}

export interface WorkspaceToolDefinition {
  tool_key: string;
  capability_code: string;
  id: string;
  group: WorkspaceToolGroup;
  slot: WorkspaceToolSlot;
  label: string;
  icon: string;
  order: number;
  shortcut?: string;
  panel_component_code: string;
  panel_component: WorkspaceToolPanelComponent;
  runtime_tool_code?: string;
  aol?: WorkspaceToolAOLDefinition;
  state_schema?: Record<string, unknown>;
}

const WORKSPACE_TOOL_ID_PATTERN = /^[a-z0-9_]+$/;
const PACK_TOOL_GROUPS = new Set<WorkspaceToolGroup>(['capability']);
const PACK_TOOL_SLOTS = new Set<WorkspaceToolSlot>([
  'workspace.right_rail.tool',
  'workbench.left_tool_rail',
  'aol.runtime.command_surface',
]);

function normalizeWorkspaceToolAOL(value: unknown): WorkspaceToolAOLDefinition | undefined {
  if (!value || typeof value !== 'object') {
    return undefined;
  }
  const candidate = value as Record<string, any>;
  const objectKind = String(candidate.object_kind || '').trim();
  const objectUri = String(candidate.object_uri || '').trim();
  const role = String(candidate.role || '').trim();
  if (!objectKind || !objectUri || !role) {
    return undefined;
  }
  return {
    object_kind: objectKind,
    object_uri: objectUri,
    role,
  };
}

export function normalizeWorkspaceToolDefinitions(
  capabilityCode: string,
  tools: unknown,
): WorkspaceToolDefinition[] {
  if (!Array.isArray(tools)) {
    return [];
  }
  const normalizedCapabilityCode = String(capabilityCode || '').trim();
  return tools
    .map((tool): WorkspaceToolDefinition | null => {
      if (!tool || typeof tool !== 'object') {
        return null;
      }
      const candidate = tool as Record<string, any>;
      const id = String(candidate.id || '').trim();
      const group = String(candidate.group || '').trim() as WorkspaceToolGroup;
      const slot = String(candidate.slot || 'workspace.right_rail.tool').trim() as WorkspaceToolSlot;
      const panelComponentCode = String(candidate.panel_component_code || '').trim();
      const panelComponent = candidate.panel_component;
      if (!normalizedCapabilityCode || !WORKSPACE_TOOL_ID_PATTERN.test(id)) {
        return null;
      }
      if (!PACK_TOOL_GROUPS.has(group)) {
        return null;
      }
      if (!PACK_TOOL_SLOTS.has(slot)) {
        return null;
      }
      if (!panelComponentCode || !panelComponent || typeof panelComponent !== 'object') {
        return null;
      }
      const panelComponentCandidate = panelComponent as Record<string, any>;
      const componentCode = String(panelComponentCandidate.code || '').trim();
      const componentPath = String(panelComponentCandidate.path || '').trim();
      if (componentCode !== panelComponentCode) {
        return null;
      }
      if (!componentPath) {
        return null;
      }
      const normalizedPanelComponent: WorkspaceToolPanelComponent = {
        code: componentCode,
        path: componentPath,
        description: String(panelComponentCandidate.description || ''),
        export: String(panelComponentCandidate.export || 'default'),
        artifact_types: Array.isArray(panelComponentCandidate.artifact_types)
          ? panelComponentCandidate.artifact_types.filter((item: unknown): item is string => typeof item === 'string')
          : [],
        playbook_codes: Array.isArray(panelComponentCandidate.playbook_codes)
          ? panelComponentCandidate.playbook_codes.filter((item: unknown): item is string => typeof item === 'string')
          : [],
        import_path: String(panelComponentCandidate.import_path || ''),
        layout_hint: panelComponentCandidate.layout_hint === 'scrollable_full_bleed'
          ? 'scrollable_full_bleed'
          : 'default',
        asset_url: typeof panelComponentCandidate.asset_url === 'string'
          ? panelComponentCandidate.asset_url
          : undefined,
        integrity: typeof panelComponentCandidate.integrity === 'string'
          ? panelComponentCandidate.integrity
          : undefined,
        runtime: typeof panelComponentCandidate.runtime === 'string'
          ? panelComponentCandidate.runtime
          : undefined,
        bytes: Number.isFinite(Number(panelComponentCandidate.bytes))
          ? Number(panelComponentCandidate.bytes)
          : undefined,
        asset_path: typeof panelComponentCandidate.asset_path === 'string'
          ? panelComponentCandidate.asset_path
          : undefined,
      };
      const runtimeToolCode = typeof candidate.runtime_tool_code === 'string'
        ? candidate.runtime_tool_code.trim() || undefined
        : undefined;
      const shortcut = typeof candidate.shortcut === 'string'
        ? candidate.shortcut.trim() || undefined
        : undefined;
      const stateSchema = candidate.state_schema && typeof candidate.state_schema === 'object' && !Array.isArray(candidate.state_schema)
        ? candidate.state_schema as Record<string, unknown>
        : undefined;
      return {
        tool_key: `${normalizedCapabilityCode}:${id}`,
        capability_code: normalizedCapabilityCode,
        id,
        group,
        slot,
        label: String(candidate.label || id).trim(),
        icon: String(candidate.icon || 'Panel').trim(),
        order: Number.isFinite(Number(candidate.order)) ? Number(candidate.order) : 1000,
        shortcut,
        panel_component_code: panelComponentCode,
        panel_component: normalizedPanelComponent,
        runtime_tool_code: runtimeToolCode,
        aol: normalizeWorkspaceToolAOL(candidate.aol),
        state_schema: stateSchema,
      };
    })
    .filter((tool): tool is WorkspaceToolDefinition => Boolean(tool))
    .sort((left, right) => left.order - right.order || left.tool_key.localeCompare(right.tool_key));
}

export async function fetchWorkspaceToolDefinitions({
  apiUrl,
  capabilityCode,
  workspaceId,
}: {
  apiUrl: string;
  capabilityCode: string;
  workspaceId?: string;
}): Promise<WorkspaceToolDefinition[]> {
  const workspaceQuery = workspaceId
    ? `?workspace_id=${encodeURIComponent(workspaceId)}`
    : '';
  const response = await fetch(
    `${apiUrl}/api/v1/capability-packs/installed-capabilities/${encodeURIComponent(capabilityCode)}/workspace-tools${workspaceQuery}`,
    { credentials: 'same-origin' },
  );
  if (!response.ok) {
    return [];
  }
  return normalizeWorkspaceToolDefinitions(capabilityCode, await response.json());
}
