import { Play } from 'lucide-react';

import type { CompositionGraphRunStatus } from '@/lib/composition-graph';
import type { MeetingTranslate } from '../meetingWorkbenchTypes';

export function DirectorGraphCompileButton({
  disabled,
  status,
  onCompile,
  showLabel = true,
  t,
}: {
  disabled: boolean;
  status: CompositionGraphRunStatus | 'idle';
  onCompile: () => void;
  showLabel?: boolean;
  t: MeetingTranslate;
}) {
  return (
    <button
      type="button"
      onClick={onCompile}
      disabled={disabled || status === 'running'}
      className="inline-flex h-8 items-center gap-1.5 rounded-md bg-blue-600 px-2.5 text-xs font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300 dark:disabled:bg-slate-800"
      data-testid="director-graph-run"
      title={t('directorGraphRun')}
    >
      <Play className="h-4 w-4" aria-hidden="true" />
      {showLabel ? <span>{status === 'running' ? t('directorGraphRunning') : t('directorGraphRun')}</span> : null}
    </button>
  );
}
