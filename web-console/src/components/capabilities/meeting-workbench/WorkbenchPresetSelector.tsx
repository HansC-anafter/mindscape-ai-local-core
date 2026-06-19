import type { WorkbenchPreset } from './meetingWorkbenchRuntimePlaneModel';
import { WORKBENCH_PRESET_OPTIONS } from './meetingWorkbenchRuntimePlaneModel';

export function WorkbenchPresetSelector({
  value,
  onChange,
  disabled = false,
}: {
  value: WorkbenchPreset;
  onChange: (preset: WorkbenchPreset) => void;
  disabled?: boolean;
}) {
  return (
    <select
      className="h-7 min-w-[8.5rem] rounded border border-slate-200 bg-white px-2 text-[11px] font-semibold text-slate-600 disabled:opacity-50 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300"
      value={value}
      disabled={disabled}
      aria-label="Workbench preset"
      data-testid="meeting-workbench-preset-select"
      onChange={(event) => onChange(event.target.value as WorkbenchPreset)}
    >
      {WORKBENCH_PRESET_OPTIONS.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}
