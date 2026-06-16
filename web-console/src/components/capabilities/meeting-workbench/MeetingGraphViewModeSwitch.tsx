import type { GraphViewMode, MeetingTranslate } from './meetingWorkbenchTypes';

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
  return (
    <div
      className={`items-center overflow-x-auto rounded-md border border-slate-200 bg-slate-50 p-0.5 dark:border-slate-800 dark:bg-slate-900 ${
        compact ? 'flex w-full' : 'flex'
      }`}
      data-testid={compact ? 'meeting-graph-view-mode-compact' : 'meeting-graph-view-mode'}
      aria-label={t('meetingWorkbenchViewModeLabel')}
    >
      {(['work', 'director', 'runs', 'trace'] as GraphViewMode[]).map((mode) => {
        const isActive = graphViewMode === mode;
        const label = mode === 'work'
          ? t('meetingWorkbenchWork')
          : mode === 'director'
            ? t('meetingWorkbenchDirectorGraph')
            : mode;
        return (
          <button
            key={mode}
            type="button"
            onClick={() => onGraphViewModeChange(mode)}
            className={`h-7 shrink-0 rounded px-2 text-[11px] font-semibold uppercase tracking-[0.08em] transition-colors ${
              compact ? 'flex-1 whitespace-nowrap' : ''
            } ${
              isActive
                ? 'bg-white text-blue-700 shadow-sm dark:bg-slate-950 dark:text-blue-300'
                : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100'
            }`}
            data-testid={`meeting-graph-view-${mode}`}
            aria-pressed={isActive}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
