import type { WorkspaceToolDefinition } from '@/lib/workspace-tools/workspace-tool-registry';

export type WorkspaceRightRegionSource =
  | 'core.builtin'
  | 'manifest.workspace_tools'
  | 'manifest.ui_components.settings';

export type WorkspaceRightRegionContributionPoint =
  | 'workspace.right_rail.tool'
  | 'workspace.settings.panel';

export type WorkspaceRightRegionGroup =
  | 'workspace'
  | 'execution'
  | 'meeting'
  | 'capability'
  | 'runtime'
  | 'tool_runtime'
  | 'data';

export interface WorkspaceRightRegionContributionV1 {
  contract_version: 'workspace-right-region/v1';
  key: string;
  id: string;
  owner_kind: 'core' | 'capability';
  owner_code: 'local-core' | string;
  source: WorkspaceRightRegionSource;
  contribution_point: WorkspaceRightRegionContributionPoint;
  group: WorkspaceRightRegionGroup;
  label: string;
  description: string;
  icon: string;
  order: number;
  badge?: {
    source: 'active_execution_count' | 'none';
  };
  visibility: {
    requires_workspace_id: boolean;
    show_when: {
      always?: boolean;
      runtime_codes?: string[];
      service_codes?: string[];
    };
  };
  placement: {
    region: 'right';
    rail_group: 'core' | 'capability';
    panel_title: string;
    panel_width_px: 320;
    scroll_policy: 'panel_body_y_auto';
    layout_hint: 'default' | 'scrollable_full_bleed';
  };
  activation: {
    trigger: 'on_user_open';
    preload: false;
    mount_policy: 'mount_only_while_active';
  };
  lifecycle: {
    hidden_frontend_polling: 'forbidden';
    close_action: 'unmount_panel_only';
    backend_job_policy: 'do_not_stop_without_explicit_user_action';
  };
  component: {
    code: string;
    path: string;
    export: string;
    import_path: string;
    props_schema?: Record<string, unknown>;
    provided_props: Array<'workspaceId' | 'apiUrl'>;
  };
  accessibility: {
    aria_label: string;
    aria_pressed: boolean;
    title: string;
    test_id: string;
  };
}

export interface SettingsPanelDefinition {
  capability_code: string;
  component_code: string;
  section: string;
  title: string;
  description?: string;
  order?: number;
  requires_workspace_id?: boolean;
  display_mode?: string;
  show_when?: {
    always?: boolean;
    runtime_codes?: string[];
    service_codes?: string[];
  };
  props_schema?: Record<string, unknown>;
  import_path: string;
  export?: string;
}

interface CoreContributionInput {
  id: 'runs_panel' | 'settings' | 'object' | 'flow';
  key?: string;
  label: string;
  description?: string;
  icon: string;
  order: number;
  group: WorkspaceRightRegionGroup;
  panelTitle?: string;
  badgeSource?: 'active_execution_count' | 'none';
  testId: string;
}

const CONTRACT_VERSION = 'workspace-right-region/v1' as const;

export const WORKSPACE_RIGHT_REGION_PANEL_WIDTH_PX = 320 as const;
export const WORKSPACE_RIGHT_REGION_PANEL_WIDTH_CLASS = 'w-80';
export const WORKSPACE_RIGHT_REGION_PANEL_BODY_CLASS = 'min-h-0 flex-1 overflow-y-auto overscroll-contain';

export const RESERVED_WORKSPACE_RIGHT_REGION_IDS = new Set([
  'runs_panel',
  'settings',
  'object',
  'flow',
]);

function baseContributionFields() {
  return {
    contract_version: CONTRACT_VERSION,
    visibility: {
      requires_workspace_id: true,
      show_when: { always: true },
    },
    placement: {
      region: 'right',
      rail_group: 'core',
      panel_title: '',
      panel_width_px: WORKSPACE_RIGHT_REGION_PANEL_WIDTH_PX,
      scroll_policy: 'panel_body_y_auto',
      layout_hint: 'default',
    },
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
  } satisfies Pick<
    WorkspaceRightRegionContributionV1,
    'contract_version' | 'visibility' | 'placement' | 'activation' | 'lifecycle'
  >;
}

export function isReservedWorkspaceRightRegionId(id: string): boolean {
  return RESERVED_WORKSPACE_RIGHT_REGION_IDS.has(id);
}

export function isPackRunsPanelContentProvider(tool: WorkspaceToolDefinition): boolean {
  return tool.id === 'runs_panel';
}

export function isPackWorkspaceRailToolVisible(tool: WorkspaceToolDefinition): boolean {
  return !isReservedWorkspaceRightRegionId(tool.id);
}

export function createCoreRightRailContribution(
  input: CoreContributionInput,
): WorkspaceRightRegionContributionV1 {
  const base = baseContributionFields();
  const panelTitle = input.panelTitle || input.label;
  return {
    ...base,
    key: input.key || `core:${input.id}`,
    id: input.id,
    owner_kind: 'core',
    owner_code: 'local-core',
    source: 'core.builtin',
    contribution_point: 'workspace.right_rail.tool',
    group: input.group,
    label: input.label,
    description: input.description || '',
    icon: input.icon,
    order: input.order,
    badge: input.badgeSource ? { source: input.badgeSource } : undefined,
    placement: {
      ...base.placement,
      rail_group: 'core',
      panel_title: panelTitle,
    },
    component: {
      code: input.id,
      path: '',
      export: 'default',
      import_path: '',
      provided_props: ['workspaceId', 'apiUrl'],
    },
    accessibility: {
      aria_label: input.label,
      aria_pressed: false,
      title: input.label,
      test_id: input.testId,
    },
  };
}

export function normalizeWorkspaceToolContribution(
  tool: WorkspaceToolDefinition,
): WorkspaceRightRegionContributionV1 | null {
  if (!isPackWorkspaceRailToolVisible(tool)) {
    return null;
  }
  const base = baseContributionFields();
  return {
    ...base,
    key: tool.tool_key,
    id: tool.id,
    owner_kind: 'capability',
    owner_code: tool.capability_code,
    source: 'manifest.workspace_tools',
    contribution_point: 'workspace.right_rail.tool',
    group: 'capability',
    label: tool.label,
    description: tool.panel_component.description || '',
    icon: tool.icon,
    order: tool.order,
    placement: {
      ...base.placement,
      rail_group: 'capability',
      panel_title: tool.label,
      layout_hint: tool.panel_component.layout_hint,
    },
    component: {
      code: tool.panel_component.code,
      path: tool.panel_component.path,
      export: tool.panel_component.export,
      import_path: tool.panel_component.import_path,
      provided_props: ['workspaceId', 'apiUrl'],
    },
    accessibility: {
      aria_label: tool.label,
      aria_pressed: false,
      title: tool.label,
      test_id: `workspace-tool-${tool.tool_key}`,
    },
  };
}

export function normalizeWorkspaceToolContributions(
  tools: WorkspaceToolDefinition[],
): WorkspaceRightRegionContributionV1[] {
  return tools
    .map(normalizeWorkspaceToolContribution)
    .filter((tool): tool is WorkspaceRightRegionContributionV1 => Boolean(tool))
    .sort((left, right) => left.order - right.order || left.key.localeCompare(right.key));
}

export function normalizeSettingsPanelContribution(
  panel: SettingsPanelDefinition,
): WorkspaceRightRegionContributionV1 {
  const base = baseContributionFields();
  const section = panel.section || 'settings';
  const group: WorkspaceRightRegionGroup = section === 'runtime-environments'
    ? 'tool_runtime'
    : section === 'data-sources'
      ? 'data'
      : 'workspace';
  return {
    ...base,
    key: `${panel.capability_code}:settings:${section}:${panel.component_code}`,
    id: panel.component_code,
    owner_kind: 'capability',
    owner_code: panel.capability_code,
    source: 'manifest.ui_components.settings',
    contribution_point: 'workspace.settings.panel',
    group,
    label: panel.title || panel.component_code,
    description: panel.description || '',
    icon: 'Settings',
    order: Number.isFinite(panel.order) ? Number(panel.order) : 100,
    visibility: {
      requires_workspace_id: Boolean(panel.requires_workspace_id),
      show_when: panel.show_when || { always: true },
    },
    placement: {
      ...base.placement,
      panel_title: panel.title || panel.component_code,
    },
    component: {
      code: panel.component_code,
      path: inferComponentPathFromImportPath(panel),
      export: panel.export || 'default',
      import_path: panel.import_path,
      props_schema: panel.props_schema,
      provided_props: panel.requires_workspace_id ? ['workspaceId', 'apiUrl'] : ['apiUrl'],
    },
    accessibility: {
      aria_label: panel.title || panel.component_code,
      aria_pressed: false,
      title: panel.title || panel.component_code,
      test_id: `workspace-settings-panel-${panel.capability_code}-${panel.component_code}`,
    },
  };
}

export function inferComponentPathFromImportPath(panel: Pick<SettingsPanelDefinition, 'component_code' | 'import_path'>): string {
  const importPath = String(panel.import_path || '').trim();
  const fileName = importPath.split('/').filter(Boolean).pop() || panel.component_code;
  const componentName = fileName.replace(/\.(tsx|ts|jsx|js)$/, '');
  return `ui/components/${componentName}.tsx`;
}
