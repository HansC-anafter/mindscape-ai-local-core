import { describe, expect, it } from 'vitest';

import {
  DEFAULT_RUNTIME_PLANE_STATE,
  resolveLegacyModeFromRuntimePlaneState,
  resolveRuntimePlaneStateFromLegacyMode,
} from './meetingWorkbenchRuntimePlaneModel';

describe('meetingWorkbenchRuntimePlaneModel', () => {
  it('keeps RUNS as the default top-level runtime plane', () => {
    expect(DEFAULT_RUNTIME_PLANE_STATE).toEqual({
      runtimePlane: 'runs',
      workbenchPreset: 'blank_run_canvas',
    });
  });

  it('maps legacy business modes into RUNS presets instead of top-level planes', () => {
    expect(resolveRuntimePlaneStateFromLegacyMode('work')).toEqual({
      runtimePlane: 'runs',
      workbenchPreset: 'context_workbench',
    });
    expect(resolveRuntimePlaneStateFromLegacyMode('director')).toEqual({
      runtimePlane: 'runs',
      workbenchPreset: 'director_graph',
    });
  });

  it('resolves runtime plane state back to the existing graph surfaces', () => {
    expect(resolveLegacyModeFromRuntimePlaneState({
      runtimePlane: 'runs',
      workbenchPreset: 'blank_run_canvas',
    })).toBe('runs');
    expect(resolveLegacyModeFromRuntimePlaneState({
      runtimePlane: 'runs',
      workbenchPreset: 'context_workbench',
    })).toBe('work');
    expect(resolveLegacyModeFromRuntimePlaneState({
      runtimePlane: 'trace',
      workbenchPreset: 'director_graph',
    })).toBe('trace');
  });
});
