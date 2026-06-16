export type AgentFreeformPanelType =
  | 'composer'
  | 'timeline'
  | 'model_feedback'
  | 'tool_calls'
  | 'approval_queue'
  | 'patch_files'
  | 'artifact_preview'
  | 'object_context'
  | 'trace_cards'
  | 'resource_state';

export type AgentFreeformLayoutOperation =
  | 'place_panel'
  | 'move_panel'
  | 'resize_panel'
  | 'group_panels'
  | 'focus_item'
  | 'pin_card'
  | 'expand_panel'
  | 'collapse_panel'
  | 'open_split_preview'
  | 'close_panel';

export interface AgentFreeformBounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface AgentFreeformLayoutIntent {
  operation: AgentFreeformLayoutOperation;
  panel_id: string;
  panel_type?: AgentFreeformPanelType;
  bounds?: AgentFreeformBounds;
  z_layer?: 'base' | 'raised' | 'focus';
  reason: string;
  trace_refs?: string[];
  turn_id?: string;
  seq?: number;
  raw_css?: unknown;
  dom_selector?: unknown;
  className?: unknown;
  component_path?: unknown;
  target?: unknown;
  refetch?: unknown;
}

export interface AgentFreeformPanel {
  id: string;
  type: AgentFreeformPanelType;
  title: string;
  bounds: AgentFreeformBounds;
  zLayer: 'base' | 'raised' | 'focus';
  pinned?: boolean;
  collapsed?: boolean;
  traceEventIds: string[];
}

export interface AgentFreeformLayoutState {
  panels: AgentFreeformPanel[];
  locked: boolean;
  selectedPanelId: string | null;
  decisions: AgentFreeformLayoutDecision[];
}

export interface AgentFreeformLayoutDecision {
  status: 'accepted' | 'rejected' | 'overridden' | 'reset' | 'locked';
  intent?: AgentFreeformLayoutIntent;
  panel_id?: string;
  reason: string;
  rule_id?: string;
  trace_refs?: string[];
}

export const AGENT_FREEFORM_WORKSPACE = {
  width: 1200,
  height: 760,
  commandBarHeight: 72,
  minPanelWidth: 220,
  minPanelHeight: 140,
  maxPanelWidth: 760,
  maxPanelHeight: 620,
  maxVisiblePanels: 8,
};

export const DEFAULT_AGENT_FREEFORM_PANELS: AgentFreeformPanel[] = [
  {
    id: 'composer',
    type: 'composer',
    title: 'Instruction',
    bounds: { x: 24, y: 24, width: 430, height: 184 },
    zLayer: 'focus',
    pinned: true,
    traceEventIds: [],
  },
  {
    id: 'timeline',
    type: 'timeline',
    title: 'Model stream',
    bounds: { x: 480, y: 24, width: 456, height: 360 },
    zLayer: 'raised',
    traceEventIds: [],
  },
  {
    id: 'approval_queue',
    type: 'approval_queue',
    title: 'Approvals',
    bounds: { x: 24, y: 232, width: 430, height: 220 },
    zLayer: 'base',
    traceEventIds: [],
  },
  {
    id: 'resource_state',
    type: 'resource_state',
    title: 'Runtime',
    bounds: { x: 960, y: 24, width: 216, height: 190 },
    zLayer: 'base',
    traceEventIds: [],
  },
  {
    id: 'trace_cards',
    type: 'trace_cards',
    title: 'Trace handoff',
    bounds: { x: 480, y: 408, width: 696, height: 220 },
    zLayer: 'base',
    traceEventIds: [],
  },
];

export function normalizeBounds(bounds: AgentFreeformBounds): AgentFreeformBounds {
  return {
    x: Math.round(bounds.x),
    y: Math.round(bounds.y),
    width: Math.round(bounds.width),
    height: Math.round(bounds.height),
  };
}
