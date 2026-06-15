import type { CompositionGraphNode, CompositionGraphNodeOption, CompositionGraphNodeType } from '@/lib/composition-graph';
import type { MeetingTranslate } from '../meetingWorkbenchTypes';

const IG_TARGET_COUNTS = [100, 300, 500] as const;

export function DirectorGraphInspector({
  node,
  nodeType,
  payloadText,
  error,
  comfyLaneOptions,
  onPayloadTextChange,
  onApplyPayload,
  onPatchPayload,
  presentation = 'inline',
  t,
}: {
  node: CompositionGraphNode | null;
  nodeType: CompositionGraphNodeType | null;
  payloadText: string;
  error: string | null;
  comfyLaneOptions: CompositionGraphNodeOption[];
  onPayloadTextChange: (value: string) => void;
  onApplyPayload: () => void;
  onPatchPayload: (patch: Record<string, unknown>) => void;
  presentation?: 'inline' | 'drawer';
  t: MeetingTranslate;
}) {
  const targetCount = Number(node?.payload.target_count || 100);
  const workflowRef = typeof node?.payload.workflow_ref === 'string' ? node.payload.workflow_ref : '';
  const drawerPresentation = presentation === 'drawer';
  return (
    <aside
      className={
        drawerPresentation
          ? 'flex min-h-0 flex-1 flex-col bg-white dark:bg-slate-950'
          : 'flex w-72 shrink-0 flex-col border-l border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950'
      }
      data-testid="director-graph-inspector"
    >
      <div className={`border-b border-slate-200 dark:border-slate-800 ${drawerPresentation ? 'px-4 pb-3 pt-4' : 'p-3'}`}>
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
        <div className={`min-h-0 flex-1 overflow-y-auto ${drawerPresentation ? 'px-4 pb-4 pt-3' : 'p-3'}`}>
          {nodeType?.id === 'ig_batch_pin_reference_set' ? (
            <div className="mb-3">
              <div className="text-xs font-semibold text-slate-600 dark:text-slate-300">{t('directorGraphBatchPinCount')}</div>
              <div className="mt-2 grid grid-cols-3 gap-1 rounded-md bg-slate-100 p-1 dark:bg-slate-900">
                {IG_TARGET_COUNTS.map((count) => (
                  <button
                    key={count}
                    type="button"
                    onClick={() => onPatchPayload({ target_count: count, source_mode: 'browser' })}
                    className={`h-8 rounded-sm text-xs font-semibold ${
                      targetCount === count
                        ? 'bg-white text-blue-700 shadow-sm dark:bg-slate-800 dark:text-blue-300'
                        : 'text-slate-600 hover:bg-white/70 dark:text-slate-300 dark:hover:bg-slate-800'
                    }`}
                    data-testid={`director-graph-target-count-${count}`}
                  >
                    {count}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          {nodeType?.id === 'comfyui_lane_adapter' ? (
            <label className="mb-3 block text-xs font-semibold text-slate-600 dark:text-slate-300">
              {t('directorGraphComfyLane')}
              <select
                value={workflowRef}
                onChange={(event) => onPatchPayload({ workflow_ref: event.target.value })}
                className="mt-2 h-9 w-full rounded border border-slate-200 bg-white px-2 text-xs font-normal text-slate-700 outline-none focus:border-blue-300 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200 dark:focus:border-blue-700"
                data-testid="director-graph-comfy-lane-select"
              >
                <option value="">{t('directorGraphNoReadyComfyLane')}</option>
                {comfyLaneOptions.map((option) => (
                  <option key={option.value} value={option.value} disabled={option.disabled}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
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
        <div className={`${drawerPresentation ? 'px-4 pb-4 pt-3' : 'p-3'} text-xs text-slate-500 dark:text-slate-400`}>
          {t('directorGraphSelectNodeHint')}
        </div>
      )}
    </aside>
  );
}
