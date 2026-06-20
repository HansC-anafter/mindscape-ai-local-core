import { RefreshCw } from 'lucide-react';

import { WorkflowEvidenceHealthSummary } from '@/components/workspace/meeting/WorkflowEvidenceHealthSummary';

import { translateMemoryStatus } from './formatters';
import { GovernedMemoryDetail } from './GovernedMemoryDetail';
import { GovernedMemoryList } from './GovernedMemoryList';
import type {
  EvidenceCoverageSummary,
  MemoryEvidenceSummary,
  MemoryTransitionAction,
  MemoryTransitionOptions,
  SuccessorDraftSuggestion,
  TransitionCue,
  TranslateFn,
  WorkspaceMemoryDetailResponse,
  WorkspaceMemoryItemSummary,
} from './types';

interface GovernedMemoryPanelViewProps {
  t: TranslateFn;
  workspaceId: string;
  apiUrl: string;
  loading: boolean;
  detailLoading: boolean;
  error: string | null;
  detailError: string | null;
  items: WorkspaceMemoryItemSummary[];
  selectedMemoryId: string | null;
  selectedDetail: WorkspaceMemoryDetailResponse | null;
  selectedItem: WorkspaceMemoryItemSummary | undefined;
  lifecycleStatus: string;
  verificationStatus: string;
  transitionReason: string;
  supersedeDraftOpen: boolean;
  successorTitle: string;
  successorClaim: string;
  successorSummary: string;
  actionError: string | null;
  actionLoading: boolean;
  evidenceTypeFilter: string;
  evidenceTypeCounts: Record<string, number>;
  filteredEvidence: MemoryEvidenceSummary[];
  evidenceCoverage: EvidenceCoverageSummary;
  primaryEvidence: MemoryEvidenceSummary | null;
  transitionCues: TransitionCue[];
  successorDraftSuggestion: SuccessorDraftSuggestion | null;
  verifyReasonSuggestion: string;
  staleReasonSuggestion: string;
  supersedeReasonSuggestion: string;
  onLifecycleStatusChange: (value: string) => void;
  onVerificationStatusChange: (value: string) => void;
  onRefresh: () => void;
  onSelectMemoryItem: (memoryItemId: string | null) => void;
  onTransitionReasonChange: (value: string) => void;
  onSupersedeDraftOpenChange: (value: boolean | ((current: boolean) => boolean)) => void;
  onSuccessorTitleChange: (value: string) => void;
  onSuccessorClaimChange: (value: string) => void;
  onSuccessorSummaryChange: (value: string) => void;
  onEvidenceTypeFilterChange: (value: string) => void;
  onTransition: (
    action: MemoryTransitionAction,
    options?: MemoryTransitionOptions
  ) => void | Promise<void>;
}

export function GovernedMemoryPanelView({
  t,
  workspaceId,
  apiUrl,
  loading,
  detailLoading,
  error,
  detailError,
  items,
  selectedMemoryId,
  selectedDetail,
  selectedItem,
  lifecycleStatus,
  verificationStatus,
  transitionReason,
  supersedeDraftOpen,
  successorTitle,
  successorClaim,
  successorSummary,
  actionError,
  actionLoading,
  evidenceTypeFilter,
  evidenceTypeCounts,
  filteredEvidence,
  evidenceCoverage,
  primaryEvidence,
  transitionCues,
  successorDraftSuggestion,
  verifyReasonSuggestion,
  staleReasonSuggestion,
  supersedeReasonSuggestion,
  onLifecycleStatusChange,
  onVerificationStatusChange,
  onRefresh,
  onSelectMemoryItem,
  onTransitionReasonChange,
  onSupersedeDraftOpenChange,
  onSuccessorTitleChange,
  onSuccessorClaimChange,
  onSuccessorSummaryChange,
  onEvidenceTypeFilterChange,
  onTransition,
}: GovernedMemoryPanelViewProps) {
  return (
    <div className="space-y-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-primary dark:text-gray-100">
              {t('governedMemory' as any) || 'Governed Memory'}
            </h2>
            <p className="text-sm text-secondary dark:text-gray-400 mt-1">
              {t('governedMemoryDescription' as any) || 'Inspect canonical memory, evidence, projections, and lifecycle transitions for this workspace.'}
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('lifecycle' as any) || 'Lifecycle'}
              </label>
              <select
                value={lifecycleStatus}
                onChange={(event) => onLifecycleStatusChange(event.target.value)}
                className="w-full sm:w-40 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              >
                <option value="">{t('all' as any) || 'All'}</option>
                <option value="candidate">{translateMemoryStatus('candidate', t)}</option>
                <option value="active">{translateMemoryStatus('active', t)}</option>
                <option value="stale">{translateMemoryStatus('stale', t)}</option>
                <option value="superseded">{translateMemoryStatus('superseded', t)}</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('verification' as any) || 'Verification'}
              </label>
              <select
                value={verificationStatus}
                onChange={(event) => onVerificationStatusChange(event.target.value)}
                className="w-full sm:w-40 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              >
                <option value="">{t('all' as any) || 'All'}</option>
                <option value="observed">{translateMemoryStatus('observed', t)}</option>
                <option value="verified">{translateMemoryStatus('verified', t)}</option>
                <option value="challenged">{translateMemoryStatus('challenged', t)}</option>
              </select>
            </div>
            <button
              onClick={onRefresh}
              className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
            >
              <RefreshCw size={14} />
              {t('refresh' as any) || 'Refresh'}
            </button>
          </div>
        </div>
      </div>

      <WorkflowEvidenceHealthSummary
        workspaceId={workspaceId}
        apiUrl={apiUrl}
        limit={8}
        showRecentSessions
      />

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <p className="text-sm text-red-800 dark:text-red-300">{error}</p>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[360px_minmax(0,1fr)] gap-4">
        <GovernedMemoryList
          t={t}
          loading={loading}
          items={items}
          selectedMemoryId={selectedMemoryId}
          onSelectMemoryItem={onSelectMemoryItem}
        />

        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-5">
          <GovernedMemoryDetail
            t={t}
            detailLoading={detailLoading}
            detailError={detailError}
            selectedDetail={selectedDetail}
            selectedItem={selectedItem}
            evidenceTypeCounts={evidenceTypeCounts}
            filteredEvidence={filteredEvidence}
            evidenceCoverage={evidenceCoverage}
            primaryEvidence={primaryEvidence}
            transitionCues={transitionCues}
            successorDraftSuggestion={successorDraftSuggestion}
            verifyReasonSuggestion={verifyReasonSuggestion}
            staleReasonSuggestion={staleReasonSuggestion}
            supersedeReasonSuggestion={supersedeReasonSuggestion}
            transitionReason={transitionReason}
            supersedeDraftOpen={supersedeDraftOpen}
            successorTitle={successorTitle}
            successorClaim={successorClaim}
            successorSummary={successorSummary}
            actionError={actionError}
            actionLoading={actionLoading}
            evidenceTypeFilter={evidenceTypeFilter}
            onSelectMemoryItem={onSelectMemoryItem}
            onTransitionReasonChange={onTransitionReasonChange}
            onSupersedeDraftOpenChange={onSupersedeDraftOpenChange}
            onSuccessorTitleChange={onSuccessorTitleChange}
            onSuccessorClaimChange={onSuccessorClaimChange}
            onSuccessorSummaryChange={onSuccessorSummaryChange}
            onEvidenceTypeFilterChange={onEvidenceTypeFilterChange}
            onTransition={onTransition}
          />
        </div>
      </div>
    </div>
  );
}
