import type { CompositionGraphNode, CompositionGraphNodeType } from '@/lib/composition-graph';
import type { MeetingTranslate } from '../meetingWorkbenchTypes';

export function DirectorGraphInspector({
  node,
  nodeType,
  payloadText,
  error,
  onPayloadTextChange,
  onApplyPayload,
  t,
}: {
  node: CompositionGraphNode | null;
  nodeType: CompositionGraphNodeType | null;
  payloadText: string;
  error: string | null;
  onPayloadTextChange: (value: string) => void;
  onApplyPayload: () => void;
  t: MeetingTranslate;
}) {
  return (
    <aside
      className="flex w-72 shrink-0 flex-col border-l border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950"
      data-testid="director-graph-inspector"
    >
      <div className="border-b border-slate-200 p-3 dark:border-slate-800">
        <div className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
          {t('directorGraphInspector')}
        </div>
        <div className="mt-1 truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
          {nodeType?.label || t('directorGraphNoSelection')}
        </div>
        {node ? (
          <div className="mt-1 truncate font-mono text-[11px] text-slate-500 dark:text-slate-400">{node.id}</div>
        ) : null}
      </div>
      {node ? (
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          <label className="block text-xs font-semibold text-slate-600 dark:text-slate-300">
            {t('directorGraphPayload')}
            <textarea
              value={payloadText}
              onChange={(event) => onPayloadTextChange(event.target.value)}
              className="mt-2 h-56 w-full resize-none rounded border border-slate-200 bg-slate-50 p-2 font-mono text-[11px] font-normal text-slate-700 outline-none focus:border-blue-300 focus:bg-white dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200 dark:focus:border-blue-700"
              data-testid="director-graph-payload-editor"
            />
          </label>
          <button
            type="button"
            onClick={onApplyPayload}
            className="mt-2 rounded border border-slate-200 px-2 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-800 dark:text-slate-200 dark:hover:bg-slate-900"
            data-testid="director-graph-apply-payload"
          >
            {t('directorGraphApplyPayload')}
          </button>
          {error ? (
            <div className="mt-2 text-xs font-medium text-rose-600 dark:text-rose-300" data-testid="director-graph-payload-error">
              {error}
            </div>
          ) : null}
          {nodeType?.payload_schema ? (
            <pre
              className="mt-3 max-h-52 overflow-auto rounded bg-slate-100 p-2 text-[10px] text-slate-500 dark:bg-slate-900 dark:text-slate-400"
              data-testid="director-graph-payload-schema"
            >
              {JSON.stringify(nodeType.payload_schema, null, 2)}
            </pre>
          ) : null}
        </div>
      ) : (
        <div className="p-3 text-xs text-slate-500 dark:text-slate-400">{t('directorGraphSelectNodeHint')}</div>
      )}
    </aside>
  );
}
