import {
  AGENT_FREEFORM_WORKSPACE,
  type AgentFreeformLayoutIntent,
  type AgentFreeformPanel,
  normalizeBounds,
} from './agentFreeformLayoutModel';

export interface AgentFreeformLayoutValidationResult {
  accepted: boolean;
  ruleId: string;
  reason: string;
  normalizedBounds?: ReturnType<typeof normalizeBounds>;
}

const ALLOWED_Z_LAYERS = new Set(['base', 'raised', 'focus']);
const SHELL_TARGETS = new Set(['global_nav', 'right_app_rail', 'workspace_sidebar', 'command_bar', 'browser_shell']);

export function validateAgentFreeformLayoutIntent(
  intent: AgentFreeformLayoutIntent,
  panels: AgentFreeformPanel[],
): AgentFreeformLayoutValidationResult {
  if (intent.raw_css || intent.dom_selector || intent.className || intent.component_path) {
    return {
      accepted: false,
      ruleId: 'no-direct-dom-or-css',
      reason: 'Agent layout intents cannot contain raw CSS, DOM selectors, class names, or component paths.',
    };
  }
  if (intent.refetch) {
    return {
      accepted: false,
      ruleId: 'no-layout-triggered-refetch',
      reason: 'Layout mutation cannot request session, graph, artifact, or transcript refetch.',
    };
  }
  if (typeof intent.target === 'string' && SHELL_TARGETS.has(intent.target)) {
    return {
      accepted: false,
      ruleId: 'protected-shell-zone',
      reason: 'Agent layout can only operate inside the RUNS workspace canvas.',
    };
  }
  if (intent.z_layer && !ALLOWED_Z_LAYERS.has(intent.z_layer)) {
    return {
      accepted: false,
      ruleId: 'invalid-z-layer',
      reason: 'z_layer must be one of base, raised, or focus.',
    };
  }
  if (intent.operation === 'close_panel') {
    return { accepted: true, ruleId: 'close-panel', reason: 'Panel close accepted.' };
  }
  if (!intent.bounds) {
    return {
      accepted: false,
      ruleId: 'missing-bounds',
      reason: 'Panel placement operations require bounds.',
    };
  }

  const bounds = normalizeBounds(intent.bounds);
  if (bounds.width < AGENT_FREEFORM_WORKSPACE.minPanelWidth || bounds.height < AGENT_FREEFORM_WORKSPACE.minPanelHeight) {
    return {
      accepted: false,
      ruleId: 'panel-too-small',
      reason: 'Panel bounds are smaller than the minimum usable size.',
    };
  }
  if (bounds.width > AGENT_FREEFORM_WORKSPACE.maxPanelWidth || bounds.height > AGENT_FREEFORM_WORKSPACE.maxPanelHeight) {
    return {
      accepted: false,
      ruleId: 'panel-too-large',
      reason: 'Panel bounds exceed the maximum workspace size.',
    };
  }
  if (bounds.x < 0 || bounds.y < 0 || bounds.x + bounds.width > AGENT_FREEFORM_WORKSPACE.width) {
    return {
      accepted: false,
      ruleId: 'workspace-bounds',
      reason: 'Panel must stay inside the RUNS workspace bounds.',
    };
  }
  if (bounds.y + bounds.height > AGENT_FREEFORM_WORKSPACE.height - AGENT_FREEFORM_WORKSPACE.commandBarHeight) {
    return {
      accepted: false,
      ruleId: 'command-bar-protected-zone',
      reason: 'Panel cannot overlap the bottom command bar protected zone.',
    };
  }
  const targetExists = panels.some((panel) => panel.id === intent.panel_id);
  const visibleCount = panels.filter((panel) => !panel.collapsed).length;
  if (!targetExists && visibleCount >= AGENT_FREEFORM_WORKSPACE.maxVisiblePanels) {
    return {
      accepted: false,
      ruleId: 'max-visible-panels',
      reason: 'Too many visible panels are already open.',
    };
  }
  return {
    accepted: true,
    ruleId: 'accepted',
    reason: 'Layout intent accepted.',
    normalizedBounds: bounds,
  };
}

export function mobilePanelOrder(panels: AgentFreeformPanel[]): AgentFreeformPanel[] {
  return [...panels].sort((a, b) => {
    if (a.id === 'composer') return -1;
    if (b.id === 'composer') return 1;
    return a.bounds.y - b.bounds.y || a.bounds.x - b.bounds.x;
  });
}
