import { Braces, Copy, Layers, Maximize2, Redo2, Save, SlidersHorizontal, Trash2, Undo2 } from 'lucide-react';

import type { CompositionGraphRunStatus } from '@/lib/composition-graph';
import type { MeetingTranslate } from '../meetingWorkbenchTypes';
import { DirectorGraphCompileButton } from './DirectorGraphCompileButton';
import type { DirectorGraphSecondarySurface } from './DirectorGraphResponsiveSurface';

const toolbarButtonClass =
  'inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-300 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-900 dark:disabled:text-slate-700';

const saveButtonClass =
  'inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-200 px-2.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-300 dark:border-slate-800 dark:text-slate-200 dark:hover:bg-slate-900 dark:disabled:text-slate-700';

function compactSurfaceButtonClass(active: boolean) {
  return `inline-flex h-8 w-8 items-center justify-center rounded-md border transition ${
    active
      ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-200'
      : 'border-slate-200 text-slate-600 hover:bg-slate-50 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-900'
  }`;
}

type SharedActionProps = {
  canCopy: boolean;
  canPaste: boolean;
  canDelete: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onCopy: () => void;
  onPaste: () => void;
  onDelete: () => void;
  t: MeetingTranslate;
};

type RunSaveActionProps = {
  meetingId: string | null;
  saving: boolean;
  saveButtonLabel: string;
  runDisabled: boolean;
  runStatus: CompositionGraphRunStatus | 'idle';
  onSave: () => void;
  onRun: () => void;
  t: MeetingTranslate;
};

function UtilityButtons({
  canCopy,
  canPaste,
  canDelete,
  onUndo,
  onRedo,
  onCopy,
  onPaste,
  onDelete,
  t,
}: SharedActionProps) {
  return (
    <>
      <button type="button" onClick={onUndo} className={toolbarButtonClass} data-testid="director-graph-undo" title={t('directorGraphUndo')}>
        <Undo2 className="h-4 w-4" aria-hidden="true" />
      </button>
      <button type="button" onClick={onRedo} className={toolbarButtonClass} data-testid="director-graph-redo" title={t('directorGraphRedo')}>
        <Redo2 className="h-4 w-4" aria-hidden="true" />
      </button>
      <button type="button" onClick={onCopy} disabled={!canCopy} className={toolbarButtonClass} data-testid="director-graph-copy" title={t('directorGraphCopy')}>
        <Copy className="h-4 w-4" aria-hidden="true" />
      </button>
      <button type="button" onClick={onPaste} disabled={!canPaste} className={toolbarButtonClass} data-testid="director-graph-paste" title={t('directorGraphPaste')}>
        <Copy className="h-4 w-4 rotate-180" aria-hidden="true" />
      </button>
      <button type="button" onClick={onDelete} disabled={!canDelete} className={toolbarButtonClass} data-testid="director-graph-delete" title={t('directorGraphDelete')}>
        <Trash2 className="h-4 w-4" aria-hidden="true" />
      </button>
      <button type="button" onClick={() => window.dispatchEvent(new Event('resize'))} className={toolbarButtonClass} data-testid="director-graph-fit" title={t('directorGraphFit')}>
        <Maximize2 className="h-4 w-4" aria-hidden="true" />
      </button>
    </>
  );
}

export function DirectorGraphDesktopToolbar(props: SharedActionProps & RunSaveActionProps) {
  return (
    <div className="flex items-center gap-1">
      <UtilityButtons {...props} />
      <button
        type="button"
        onClick={props.onSave}
        disabled={!props.meetingId || props.saving}
        className={saveButtonClass}
        data-testid="director-graph-save"
        title={props.t('directorGraphSave')}
      >
        <Save className="h-4 w-4" aria-hidden="true" />
        <span>{props.saveButtonLabel}</span>
      </button>
      <DirectorGraphCompileButton disabled={props.runDisabled} status={props.runStatus} onCompile={props.onRun} t={props.t} />
    </div>
  );
}

export function DirectorGraphCompactPrimaryActions({
  meetingId,
  saving,
  saveButtonLabel,
  runDisabled,
  runStatus,
  onSave,
  onRun,
  mobileViewport,
  t,
}: RunSaveActionProps & { mobileViewport: boolean }) {
  return (
    <>
      <button
        type="button"
        onClick={onSave}
        disabled={!meetingId || saving}
        className={saveButtonClass}
        data-testid="director-graph-save"
        title={t('directorGraphSave')}
      >
        <Save className="h-4 w-4" aria-hidden="true" />
        <span className={mobileViewport ? 'sr-only' : undefined}>{saveButtonLabel}</span>
      </button>
      <DirectorGraphCompileButton disabled={runDisabled} status={runStatus} onCompile={onRun} showLabel={!mobileViewport} t={t} />
    </>
  );
}

export function DirectorGraphCompactUtilityActions({
  compactSurface,
  onToggleCompactSurface,
  ...utilityProps
}: SharedActionProps & {
  compactSurface: DirectorGraphSecondarySurface | null;
  onToggleCompactSurface: (surface: DirectorGraphSecondarySurface) => void;
}) {
  return (
    <>
      <button
        type="button"
        onClick={() => onToggleCompactSurface('palette')}
        className={compactSurfaceButtonClass(compactSurface === 'palette')}
        data-testid="director-graph-toggle-palette"
        title={utilityProps.t('directorGraphPalette')}
        aria-pressed={compactSurface === 'palette'}
      >
        <Layers className="h-4 w-4" aria-hidden="true" />
      </button>
      <button
        type="button"
        onClick={() => onToggleCompactSurface('inspector')}
        className={compactSurfaceButtonClass(compactSurface === 'inspector')}
        data-testid="director-graph-toggle-inspector"
        title={utilityProps.t('directorGraphInspector')}
        aria-pressed={compactSurface === 'inspector'}
      >
        <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
      </button>
      <button
        type="button"
        onClick={() => onToggleCompactSurface('json')}
        className={compactSurfaceButtonClass(compactSurface === 'json')}
        data-testid="director-graph-toggle-json"
        title={utilityProps.t('directorGraphJsonTitle')}
        aria-pressed={compactSurface === 'json'}
      >
        <Braces className="h-4 w-4" aria-hidden="true" />
      </button>
      <UtilityButtons {...utilityProps} />
    </>
  );
}
