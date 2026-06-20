import { CheckCircle2, Clock3, GitBranchPlus } from 'lucide-react';

import {
  cueToneClass,
} from './formatters';
import type {
  EvidenceCoverageSummary,
  MemoryEvidenceSummary,
  MemoryTransitionAction,
  MemoryTransitionOptions,
  SuccessorDraftSuggestion,
  TransitionCue,
  TranslateFn,
  WorkspaceMemoryItemSummary,
} from './types';

interface GovernedMemoryTransitionSectionProps {
  t: TranslateFn;
  selectedItem: WorkspaceMemoryItemSummary;
  evidenceCoverage: EvidenceCoverageSummary;
  transitionCues: TransitionCue[];
  transitionReason: string;
  actionError: string | null;
  actionLoading: boolean;
  supersedeDraftOpen: boolean;
  successorDraftSuggestion: SuccessorDraftSuggestion | null;
  primaryEvidence: MemoryEvidenceSummary | null;
  successorTitle: string;
  successorClaim: string;
  successorSummary: string;
  verifyReasonSuggestion: string;
  staleReasonSuggestion: string;
  supersedeReasonSuggestion: string;
  onTransitionReasonChange: (value: string) => void;
  onSupersedeDraftOpenChange: (value: boolean | ((current: boolean) => boolean)) => void;
  onSuccessorTitleChange: (value: string) => void;
  onSuccessorClaimChange: (value: string) => void;
  onSuccessorSummaryChange: (value: string) => void;
  onTransition: (
    action: MemoryTransitionAction,
    options?: MemoryTransitionOptions
  ) => void | Promise<void>;
}

export function GovernedMemoryTransitionSection({
  t,
  selectedItem,
  evidenceCoverage,
  transitionCues,
  transitionReason,
  actionError,
  actionLoading,
  supersedeDraftOpen,
  successorDraftSuggestion,
  primaryEvidence,
  successorTitle,
  successorClaim,
  successorSummary,
  verifyReasonSuggestion,
  staleReasonSuggestion,
  supersedeReasonSuggestion,
  onTransitionReasonChange,
  onSupersedeDraftOpenChange,
  onSuccessorTitleChange,
  onSuccessorClaimChange,
  onSuccessorSummaryChange,
  onTransition,
}: GovernedMemoryTransitionSectionProps) {
  return (
    <div className="rounded-lg border border-default dark:border-gray-700 p-4 space-y-3">
      <div className="text-sm font-semibold text-primary dark:text-gray-100">
        {t('memoryTransitions' as any) || 'Memory Transitions'}
      </div>
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-2">
        <div className="rounded border border-default dark:border-gray-700 bg-surface-accent dark:bg-gray-900/40 px-3 py-2">
          <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400">
            {t('deliberation' as any) || 'Deliberation'}
          </div>
          <div className="mt-1 text-sm font-semibold text-primary dark:text-gray-100">
            {evidenceCoverage.deliberation}
          </div>
        </div>
        <div className="rounded border border-default dark:border-gray-700 bg-surface-accent dark:bg-gray-900/40 px-3 py-2">
          <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400">
            {t('execution' as any) || 'Execution'}
          </div>
          <div className="mt-1 text-sm font-semibold text-primary dark:text-gray-100">
            {evidenceCoverage.execution}
          </div>
        </div>
        <div className="rounded border border-default dark:border-gray-700 bg-surface-accent dark:bg-gray-900/40 px-3 py-2">
          <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400">
            {t('governance' as any) || 'Governance'}
          </div>
          <div className="mt-1 text-sm font-semibold text-primary dark:text-gray-100">
            {evidenceCoverage.governance}
          </div>
        </div>
        <div className="rounded border border-default dark:border-gray-700 bg-surface-accent dark:bg-gray-900/40 px-3 py-2">
          <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400">
            {t('supportLinks' as any) || 'Support Links'}
          </div>
          <div className="mt-1 text-sm font-semibold text-primary dark:text-gray-100">
            {evidenceCoverage.support}
          </div>
        </div>
      </div>
      <div className="space-y-2">
        {transitionCues.map((cue) => (
          <div
            key={cue.id}
            className={`rounded border px-3 py-2 ${cueToneClass(cue.tone)}`}
          >
            <div className="text-sm font-medium">{cue.title}</div>
            <div className="mt-1 text-xs leading-5 opacity-90">{cue.body}</div>
          </div>
        ))}
      </div>
      <textarea
        value={transitionReason}
        onChange={(event) => onTransitionReasonChange(event.target.value)}
        placeholder={t('transitionReasonPlaceholder' as any) || 'Optional reason for this transition'}
        className="w-full min-h-[88px] px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
      />
      <div className="flex flex-wrap gap-2">
        {selectedItem.lifecycle_status === 'candidate' && (
          <button
            type="button"
            onClick={() => onTransitionReasonChange(verifyReasonSuggestion)}
            className="inline-flex items-center gap-2 px-2.5 py-1.5 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
          >
            {t('useVerifyReason' as any) || 'Use verify reason'}
          </button>
        )}
        {selectedItem.lifecycle_status === 'active' && (
          <>
            <button
              type="button"
              onClick={() => onTransitionReasonChange(staleReasonSuggestion)}
              className="inline-flex items-center gap-2 px-2.5 py-1.5 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
            >
              {t('useStaleReason' as any) || 'Use stale reason'}
            </button>
            <button
              type="button"
              onClick={() => onTransitionReasonChange(supersedeReasonSuggestion)}
              className="inline-flex items-center gap-2 px-2.5 py-1.5 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
            >
              {t('useSupersedeReason' as any) || 'Use supersede reason'}
            </button>
          </>
        )}
      </div>
      {actionError && (
        <div className="text-sm text-red-700 dark:text-red-300">{actionError}</div>
      )}
      <div className="flex flex-wrap gap-2">
        {selectedItem.lifecycle_status === 'candidate' && (
          <button
            onClick={() => void onTransition('verify')}
            disabled={actionLoading}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-60"
          >
            <CheckCircle2 size={14} />
            {t('verify' as any) || 'Verify'}
          </button>
        )}
        {selectedItem.lifecycle_status === 'active' && (
          <>
            <button
              onClick={() => void onTransition('stale')}
              disabled={actionLoading}
              className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded bg-slate-600 text-white hover:bg-slate-700 disabled:opacity-60"
            >
              <Clock3 size={14} />
              {t('markStale' as any) || 'Mark Stale'}
            </button>
            <button
              onClick={() => onSupersedeDraftOpenChange((value) => !value)}
              disabled={actionLoading}
              className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-60"
            >
              <GitBranchPlus size={14} />
              {t('supersede' as any) || 'Supersede'}
            </button>
          </>
        )}
      </div>

      {supersedeDraftOpen && selectedItem.lifecycle_status === 'active' && (
        <div className="grid grid-cols-1 gap-3 border-t border-default dark:border-gray-700 pt-3">
          {successorDraftSuggestion && (
            <div className="rounded border border-default dark:border-gray-700 bg-surface-accent dark:bg-gray-900/40 px-3 py-3">
              <div className="text-xs font-medium text-secondary dark:text-gray-400">
                {t('suggestedSuccessorDraft' as any) || 'Suggested successor draft'}
              </div>
              <div className="mt-1 text-sm text-gray-800 dark:text-gray-200">
                {t('primaryAnchor' as any) || 'Primary anchor'}:{' '}
                {successorDraftSuggestion?.primary_evidence_id ||
                  primaryEvidence?.evidence_id ||
                  (t('currentMemoryClaim' as any) || 'current memory claim')}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => {
                    onSuccessorTitleChange(successorDraftSuggestion.title);
                    onSuccessorClaimChange(successorDraftSuggestion.claim);
                    onSuccessorSummaryChange(successorDraftSuggestion.summary);
                  }}
                  className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                >
                  {t('useSuggestedDraft' as any) || 'Use Suggested Draft'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    onSuccessorTitleChange('');
                    onSuccessorClaimChange('');
                    onSuccessorSummaryChange('');
                  }}
                  className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                >
                  {t('clearDraft' as any) || 'Clear Draft'}
                </button>
              </div>
            </div>
          )}
          <input
            value={successorTitle}
            onChange={(event) => onSuccessorTitleChange(event.target.value)}
            placeholder={t('successorTitle' as any) || 'Successor title (optional)'}
            className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          />
          <textarea
            value={successorClaim}
            onChange={(event) => onSuccessorClaimChange(event.target.value)}
            placeholder={t('successorClaim' as any) || 'Successor claim (optional)'}
            className="w-full min-h-[88px] px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          />
          <textarea
            value={successorSummary}
            onChange={(event) => onSuccessorSummaryChange(event.target.value)}
            placeholder={t('successorSummary' as any) || 'Successor summary (optional)'}
            className="w-full min-h-[88px] px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
          />
          <div className="flex justify-end">
            <button
              onClick={() =>
                void onTransition('supersede', {
                  successor_title: successorTitle || undefined,
                  successor_claim: successorClaim || undefined,
                  successor_summary: successorSummary || undefined,
                })
              }
              disabled={actionLoading}
              className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-60"
            >
              <GitBranchPlus size={14} />
              {t('createSuccessor' as any) || 'Create Successor'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
