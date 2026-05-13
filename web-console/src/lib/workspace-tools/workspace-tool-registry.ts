export type WorkspaceToolGroup = 'workspace' | 'execution' | 'meeting' | 'capability';

export interface WorkspaceToolPanelComponent {
  code: string;
  path: string;
  description: string;
  export: string;
  artifact_types: string[];
  playbook_codes: string[];
  import_path: string;
  layout_hint: 'default' | 'scrollable_full_bleed';
}

export interface WorkspaceToolDefinition {
  tool_key: string;
  capability_code: string;
  id: string;
  group: WorkspaceToolGroup;
  label: string;
  icon: string;
  order: number;
  panel_component_code: string;
  panel_component: WorkspaceToolPanelComponent;
}

const WORKSPACE_TOOL_ID_PATTERN = /^[a-z0-9_]+$/;
const PACK_TOOL_GROUPS = new Set<WorkspaceToolGroup>(['capability']);

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
      const panelComponentCode = String(candidate.panel_component_code || '').trim();
      const panelComponent = candidate.panel_component;
      if (!normalizedCapabilityCode || !WORKSPACE_TOOL_ID_PATTERN.test(id)) {
        return null;
      }
      if (!PACK_TOOL_GROUPS.has(group)) {
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
      };
      return {
        tool_key: `${normalizedCapabilityCode}:${id}`,
        capability_code: normalizedCapabilityCode,
        id,
        group,
        label: String(candidate.label || id).trim(),
        icon: String(candidate.icon || 'Panel').trim(),
        order: Number.isFinite(Number(candidate.order)) ? Number(candidate.order) : 1000,
        panel_component_code: panelComponentCode,
        panel_component: normalizedPanelComponent,
      };
    })
    .filter((tool): tool is WorkspaceToolDefinition => Boolean(tool))
    .sort((left, right) => left.order - right.order || left.tool_key.localeCompare(right.tool_key));
}

export async function fetchWorkspaceToolDefinitions({
  apiUrl,
  capabilityCode,
}: {
  apiUrl: string;
  capabilityCode: string;
}): Promise<WorkspaceToolDefinition[]> {
  const response = await fetch(
    `${apiUrl}/api/v1/capability-packs/installed-capabilities/${encodeURIComponent(capabilityCode)}/workspace-tools`,
    { credentials: 'same-origin' },
  );
  if (!response.ok) {
    return [];
  }
  return normalizeWorkspaceToolDefinitions(capabilityCode, await response.json());
}
