import type { CompositionGraphImportExportPayload } from '@/lib/composition-graph';
import type { MeetingTranslate } from '../meetingWorkbenchTypes';

export function DirectorGraphImportExport({
  value,
  error,
  onChange,
  onExport,
  onImport,
  onInvalidImport,
  t,
}: {
  value: string;
  error: string | null;
  onChange: (value: string) => void;
  onExport: () => void;
  onImport: (payload: CompositionGraphImportExportPayload) => void;
  onInvalidImport: (message: string) => void;
  t: MeetingTranslate;
}) {
  return (
    <div className="flex min-h-0 flex-col gap-2 border-t border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-950">
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
          {t('directorGraphJsonTitle')}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onExport}
            className="rounded border border-slate-200 px-2 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-800 dark:text-slate-200 dark:hover:bg-slate-900"
            data-testid="director-graph-export"
          >
            {t('directorGraphExport')}
          </button>
          <button
            type="button"
            onClick={() => {
              try {
                onImport(JSON.parse(value) as CompositionGraphImportExportPayload);
              } catch (cause) {
                onInvalidImport(cause instanceof Error ? cause.message : 'Invalid composition graph JSON.');
              }
            }}
            className="rounded border border-slate-200 px-2 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-800 dark:text-slate-200 dark:hover:bg-slate-900"
            data-testid="director-graph-import"
          >
            {t('directorGraphImport')}
          </button>
        </div>
      </div>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-28 resize-none rounded border border-slate-200 bg-slate-50 p-2 font-mono text-[11px] text-slate-700 outline-none focus:border-blue-300 focus:bg-white dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200 dark:focus:border-blue-700"
        data-testid="director-graph-json"
        aria-label={t('directorGraphJsonTitle')}
      />
      {error ? (
        <div className="text-xs font-medium text-rose-600 dark:text-rose-300" data-testid="director-graph-import-error">
          {error}
        </div>
      ) : null}
    </div>
  );
}
