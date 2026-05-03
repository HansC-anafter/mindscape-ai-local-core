import {
  Box,
  Cpu,
  FileText,
  GitBranch,
  ListTree,
  MessageSquare,
  Wrench,
  type LucideIcon,
} from 'lucide-react';

import type { GraphViewMode, InspectorTab, MeetingGraphLaneConfig } from './meetingWorkbenchTypes';

export type InspectorTabConfig = {
  id: InspectorTab;
  label: string;
  icon: LucideIcon;
};

export const INSPECTOR_TABS: InspectorTabConfig[] = [
  { id: 'object', label: 'Object', icon: Box },
  { id: 'runtime', label: 'Runtime', icon: Cpu },
  { id: 'session', label: 'Session', icon: FileText },
  { id: 'trace', label: 'Trace', icon: ListTree },
  { id: 'graph', label: 'Graph', icon: GitBranch },
  { id: 'prompts', label: 'Prompts', icon: MessageSquare },
  { id: 'patch', label: 'Patch', icon: Wrench },
];

export const WORK_INSPECTOR_TABS: InspectorTabConfig[] = [
  { id: 'object', label: 'Summary', icon: Box },
  { id: 'graph', label: 'Guidance', icon: GitBranch },
  { id: 'prompts', label: 'Actions', icon: MessageSquare },
  { id: 'session', label: 'Context', icon: FileText },
  { id: 'runtime', label: 'Runtime', icon: Cpu },
  { id: 'patch', label: 'Review', icon: Wrench },
  { id: 'trace', label: 'Trace', icon: ListTree },
];

export function getInspectorTabs(graphViewMode: GraphViewMode): InspectorTabConfig[] {
  return graphViewMode === 'work' ? WORK_INSPECTOR_TABS : INSPECTOR_TABS;
}

export const GRAPH_LANES: MeetingGraphLaneConfig[] = [
  { id: 'context', label: 'Context', description: 'Session and object' },
  { id: 'graph', label: 'Object Graph', description: 'Bounded relations' },
  { id: 'commands', label: 'Commands', description: 'Issued instructions' },
  { id: 'runs', label: 'Runs', description: 'Tools and execution' },
  { id: 'outputs', label: 'Outputs', description: 'Responses' },
  { id: 'artifacts', label: 'Artifacts', description: 'Landed assets' },
  { id: 'next', label: 'Next', description: 'New instruction' },
];

export const WORK_GRAPH_LANES: MeetingGraphLaneConfig[] = [
  { id: 'context', label: 'Focus', description: 'Session objects' },
  { id: 'graph', label: 'Guidance', description: 'Context and relations' },
  { id: 'commands', label: 'Command Ledger', description: 'User intent' },
  { id: 'runs', label: 'Runtime', description: 'Tool calls' },
  { id: 'outputs', label: 'Outcomes', description: 'Results and proof' },
  { id: 'artifacts', label: 'Assets', description: 'Landed outputs' },
  { id: 'next', label: 'Next', description: 'Next operation' },
];

export const MIN_CANVAS_ZOOM = 0.7;
export const MAX_CANVAS_ZOOM = 1.6;
export const CANVAS_ZOOM_STEP = 0.1;
export const MIN_DISCRETE_WHEEL_ZOOM_DELTA = 80;
export const MENTION_TOKEN_PATTERN = /(^|[\s，,、:：])(@[A-Za-z_][A-Za-z0-9_:-]*)/g;
