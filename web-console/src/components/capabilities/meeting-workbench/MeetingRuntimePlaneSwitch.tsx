import type { RuntimePlane } from './meetingWorkbenchRuntimePlaneModel';

const RUNTIME_PLANES: RuntimePlane[] = ['runs', 'trace'];

export function MeetingRuntimePlaneSwitch({
  runtimePlane,
  onRuntimePlaneChange,
  compact = false,
}: {
  runtimePlane: RuntimePlane;
  onRuntimePlaneChange: (plane: RuntimePlane) => void;
  compact?: boolean;
}) {
  return (
    <div className={`flex ${compact ? 'min-w-[9rem] flex-1' : ''}`} data-testid="meeting-runtime-plane-switch">
      {RUNTIME_PLANES.map((plane) => {
        const isActive = runtimePlane === plane;
        return (
          <button
            key={plane}
            type="button"
            onClick={() => onRuntimePlaneChange(plane)}
            className={`h-7 shrink-0 rounded px-2 text-[11px] font-semibold uppercase tracking-[0.08em] transition-colors ${
              compact ? 'flex-1 whitespace-nowrap' : ''
            } ${
              isActive
                ? 'bg-white text-blue-700 shadow-sm dark:bg-slate-950 dark:text-blue-300'
                : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100'
            }`}
            data-testid={`meeting-graph-view-${plane}`}
            data-runtime-plane={plane}
            aria-pressed={isActive}
          >
            {plane}
          </button>
        );
      })}
    </div>
  );
}
