import { Play } from 'lucide-react';

import type { CompositionGraphCompileStatus } from '@/lib/composition-graph';
import type { MeetingTranslate } from '../meetingWorkbenchTypes';

export function DirectorGraphCompileButton({
  disabled,
  status,
  onCompile,
  t,
}: {
  disabled: boolean;
  status: CompositionGraphCompileStatus | 'idle' | 'running';
  onCompile: () => void;
  t: MeetingTranslate;
}) {
  return (
    <button
      type="button"
      onClick={onCompile}
      disabled={disabled || status === 'running'}
      className="inline-flex h-8 items-center gap-1.5 rounded-md bg-blue-600 px-2.5 text-xs font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300 dark:disabled:bg-slate-800"
      data-testid="director-graph-compile"
      title={t('directorGraphCompile')}
    >
      <Play className="h-4 w-4" aria-hidden="true" />
      <span>{status === 'running' ? t('directorGraphCompiling') : t('directorGraphCompile')}</span>
    </button>
  );
}
