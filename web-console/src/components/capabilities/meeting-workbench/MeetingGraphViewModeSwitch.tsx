import type { GraphViewMode, MeetingTranslate } from './meetingWorkbenchTypes';
import { MeetingRuntimePlaneSwitch } from './MeetingRuntimePlaneSwitch';
import {
  resolveLegacyModeFromRuntimePlaneState,
  resolveRuntimePlaneStateFromLegacyMode,
  type RuntimePlane,
  type WorkbenchPreset,
} from './meetingWorkbenchRuntimePlaneModel';
import { WorkbenchPresetSelector } from './WorkbenchPresetSelector';

export function MeetingGraphViewModeSwitch({
  graphViewMode,
  onGraphViewModeChange,
  t,
  compact = false,
}: {
  graphViewMode: GraphViewMode;
  onGraphViewModeChange: (mode: GraphViewMode) => void;
  t: MeetingTranslate;
  compact?: boolean;
}) {
  const runtimePlaneState = resolveRuntimePlaneStateFromLegacyMode(graphViewMode);
  const handleRuntimePlaneChange = (runtimePlane: RuntimePlane) => {
    onGraphViewModeChange(resolveLegacyModeFromRuntimePlaneState({
      runtimePlane,
      workbenchPreset: runtimePlane === 'runs' ? runtimePlaneState.workbenchPreset : 'blank_run_canvas',
    }));
  };
  const handlePresetChange = (workbenchPreset: WorkbenchPreset) => {
    onGraphViewModeChange(resolveLegacyModeFromRuntimePlaneState({
      runtimePlane: 'runs',
      workbenchPreset,
    }));
  };

  return (
    <div
      className={`items-center gap-1 overflow-x-auto rounded-md border border-slate-200 bg-slate-50 p-0.5 dark:border-slate-800 dark:bg-slate-900 ${
        compact ? 'flex w-full' : 'flex'
      }`}
      data-testid={compact ? 'meeting-graph-view-mode-compact' : 'meeting-graph-view-mode'}
      aria-label={t('meetingWorkbenchViewModeLabel')}
    >
      <MeetingRuntimePlaneSwitch
        runtimePlane={runtimePlaneState.runtimePlane}
        onRuntimePlaneChange={handleRuntimePlaneChange}
        compact={compact}
      />
      <WorkbenchPresetSelector
        value={runtimePlaneState.workbenchPreset}
        onChange={handlePresetChange}
        disabled={runtimePlaneState.runtimePlane === 'trace'}
      />
    </div>
  );
}
