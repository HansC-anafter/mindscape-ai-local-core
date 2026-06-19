import type { GraphViewMode } from './meetingWorkbenchTypes';

export type RuntimePlane = 'runs' | 'trace';
export type WorkbenchPreset = 'blank_run_canvas' | 'context_workbench' | 'director_graph';

export interface RuntimePlaneState {
  runtimePlane: RuntimePlane;
  workbenchPreset: WorkbenchPreset;
}

export const DEFAULT_RUNTIME_PLANE_STATE: RuntimePlaneState = {
  runtimePlane: 'runs',
  workbenchPreset: 'blank_run_canvas',
};

export const WORKBENCH_PRESET_OPTIONS: Array<{
  value: WorkbenchPreset;
  label: string;
}> = [
  { value: 'blank_run_canvas', label: 'Blank canvas' },
  { value: 'context_workbench', label: 'Context workbench' },
  { value: 'director_graph', label: 'Director graph' },
];

const LEGACY_MODE_BY_PRESET: Record<WorkbenchPreset, GraphViewMode> = {
  blank_run_canvas: 'runs',
  context_workbench: 'work',
  director_graph: 'director',
};

export function resolveRuntimePlaneStateFromLegacyMode(mode: GraphViewMode): RuntimePlaneState {
  if (mode === 'trace') {
    return { runtimePlane: 'trace', workbenchPreset: 'blank_run_canvas' };
  }
  if (mode === 'director') {
    return { runtimePlane: 'runs', workbenchPreset: 'director_graph' };
  }
  if (mode === 'work') {
    return { runtimePlane: 'runs', workbenchPreset: 'context_workbench' };
  }
  return DEFAULT_RUNTIME_PLANE_STATE;
}

export function resolveLegacyModeFromRuntimePlaneState(state: RuntimePlaneState): GraphViewMode {
  if (state.runtimePlane === 'trace') {
    return 'trace';
  }
  return LEGACY_MODE_BY_PRESET[state.workbenchPreset];
}
