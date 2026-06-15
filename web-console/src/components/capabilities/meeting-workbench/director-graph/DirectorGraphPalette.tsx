import { Layers } from 'lucide-react';

import type { CompositionGraphContract, CompositionGraphNodeType } from '@/lib/composition-graph';
import type { MeetingTranslate } from '../meetingWorkbenchTypes';

export function DirectorGraphPalette({
  contracts,
  nodeTypes,
  selectedPrimaryPack,
  onSelectPrimaryPack,
  onAddNode,
  presentation = 'inline',
  t,
}: {
  contracts: CompositionGraphContract[];
  nodeTypes: CompositionGraphNodeType[];
  selectedPrimaryPack: string | null;
  onSelectPrimaryPack: (capabilityCode: string | null) => void;
  onAddNode: (nodeType: CompositionGraphNodeType) => void;
  presentation?: 'inline' | 'drawer';
  t: MeetingTranslate;
}) {
  const drawerPresentation = presentation === 'drawer';

  return (
    <aside
      className={
        drawerPresentation
          ? 'flex min-h-0 flex-1 flex-col bg-white dark:bg-slate-950'
          : 'flex w-64 shrink-0 flex-col border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950'
      }
      data-testid="director-graph-palette"
    >
      <div className={`border-b border-slate-200 dark:border-slate-800 ${drawerPresentation ? 'px-4 pb-3 pt-4' : 'p-3'}`}>
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
          <Layers className="h-4 w-4" aria-hidden="true" />
          {t('directorGraphPalette')}
        </div>
        <label className="mt-3 block text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
          {t('directorGraphPrimaryPack')}
          <select
            value={selectedPrimaryPack || ''}
            onChange={(event) => onSelectPrimaryPack(event.target.value || null)}
            className="mt-1 h-8 w-full rounded border border-slate-200 bg-white px-2 text-xs font-medium normal-case tracking-normal text-slate-700 outline-none dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
            data-testid="director-graph-primary-pack"
          >
            <option value="">{t('directorGraphNoPack')}</option>
            {contracts.map((contract) => (
              <option key={contract.capability_code} value={contract.capability_code}>
                {contract.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className={`min-h-0 flex-1 overflow-y-auto ${drawerPresentation ? 'px-4 pb-4' : 'p-2'}`}>
        {nodeTypes.map((nodeType) => (
          <button
            key={`${nodeType.source}:${nodeType.capability_code || 'core'}:${nodeType.id}`}
            type="button"
            draggable
            onDragStart={(event) => {
              event.dataTransfer.setData('application/x-composition-graph-node-type', nodeType.id);
              event.dataTransfer.effectAllowed = 'copy';
            }}
            onClick={() => onAddNode(nodeType)}
            className="mb-2 w-full rounded-md border border-slate-200 bg-slate-50 p-2 text-left transition hover:border-blue-200 hover:bg-blue-50 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-blue-800 dark:hover:bg-blue-950/30"
            data-testid={`director-graph-node-type-${nodeType.id}`}
          >
            <div className="flex items-start justify-between gap-2">
              <span className="text-xs font-semibold text-slate-800 dark:text-slate-100">{nodeType.label}</span>
              <span className="rounded bg-white px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-500 dark:bg-slate-950 dark:text-slate-400">
                {nodeType.source}
              </span>
            </div>
            <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-slate-500 dark:text-slate-400">
              {nodeType.description || nodeType.category || nodeType.id}
            </div>
          </button>
        ))}
      </div>
    </aside>
  );
}
