import { formatLocalDateTime } from '@/lib/time';

import {
  badgeClass,
  prettyLabel,
  translateMemoryStatus,
} from './formatters';
import { GovernedMemoryEvidenceSection } from './GovernedMemoryEvidenceSection';
import {
  GovernedMemoryEdgesSection,
  GovernedMemoryRelatedSections,
  GovernedMemoryVersionsSection,
} from './GovernedMemoryRelatedSections';
import { GovernedMemoryTransitionSection } from './GovernedMemoryTransitionSection';
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

interface GovernedMemoryDetailProps {
  t: TranslateFn;
  detailLoading: boolean;
  detailError: string | null;
  selectedDetail: WorkspaceMemoryDetailResponse | null;
  selectedItem: WorkspaceMemoryItemSummary | undefined;
  evidenceTypeCounts: Record<string, number>;
  filteredEvidence: MemoryEvidenceSummary[];
  evidenceCoverage: EvidenceCoverageSummary;
  primaryEvidence: MemoryEvidenceSummary | null;
  transitionCues: TransitionCue[];
  successorDraftSuggestion: SuccessorDraftSuggestion | null;
  verifyReasonSuggestion: string;
  staleReasonSuggestion: string;
  supersedeReasonSuggestion: string;
  transitionReason: string;
  supersedeDraftOpen: boolean;
  successorTitle: string;
  successorClaim: string;
  successorSummary: string;
  actionError: string | null;
  actionLoading: boolean;
  evidenceTypeFilter: string;
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

export function GovernedMemoryDetail({
  t,
  detailLoading,
  detailError,
  selectedDetail,
  selectedItem,
  evidenceTypeCounts,
  filteredEvidence,
  evidenceCoverage,
  primaryEvidence,
  transitionCues,
  successorDraftSuggestion,
  verifyReasonSuggestion,
  staleReasonSuggestion,
  supersedeReasonSuggestion,
  transitionReason,
  supersedeDraftOpen,
  successorTitle,
  successorClaim,
  successorSummary,
  actionError,
  actionLoading,
  evidenceTypeFilter,
  onSelectMemoryItem,
  onTransitionReasonChange,
  onSupersedeDraftOpenChange,
  onSuccessorTitleChange,
  onSuccessorClaimChange,
  onSuccessorSummaryChange,
  onEvidenceTypeFilterChange,
  onTransition,
}: GovernedMemoryDetailProps) {
  if (detailLoading) {
    return (
      <div className="text-center py-8 text-secondary dark:text-gray-400">
        {t('loading' as any) || 'Loading...'}
      </div>
    );
  }

  if (detailError) {
    return (
      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
        <p className="text-sm text-red-800 dark:text-red-300">{detailError}</p>
      </div>
    );
  }

  if (!selectedDetail || !selectedItem) {
    return (
      <div className="text-center py-8 text-secondary dark:text-gray-400">
        {t('selectMemoryItem' as any) || 'Select a memory item to inspect its detail.'}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex flex-wrap gap-2 mb-2">
            <span className={`px-2 py-1 text-xs font-medium rounded ${badgeClass(selectedItem.lifecycle_status)}`}>
              {translateMemoryStatus(selectedItem.lifecycle_status, t)}
            </span>
            <span className={`px-2 py-1 text-xs font-medium rounded ${badgeClass(selectedItem.verification_status)}`}>
              {translateMemoryStatus(selectedItem.verification_status, t)}
            </span>
            <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
              {prettyLabel(selectedItem.kind)}
            </span>
            <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
              {prettyLabel(selectedItem.layer)}
            </span>
          </div>
          <h3 className="text-xl font-semibold text-primary dark:text-gray-100">
            {selectedItem.title}
          </h3>
          <p className="text-xs text-secondary dark:text-gray-400 mt-1 font-mono break-all">
            {selectedItem.id}
          </p>
          {selectedItem.supersedes_memory_id && (
            <button
              onClick={() => onSelectMemoryItem(selectedItem.supersedes_memory_id || null)}
              className="mt-2 inline-flex items-center px-2.5 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
            >
              {t('openPredecessor' as any) || 'Open Predecessor'}: {selectedItem.supersedes_memory_id}
            </button>
          )}
        </div>
        <div className="text-xs text-secondary dark:text-gray-400 space-y-1">
          <div>{t('observedAt' as any) || 'Observed'}: {formatLocalDateTime(selectedItem.observed_at)}</div>
          <div>{t('updatedAt' as any) || 'Updated'}: {formatLocalDateTime(selectedItem.updated_at)}</div>
          {selectedItem.last_confirmed_at && (
            <div>{t('confirmedAt' as any) || 'Confirmed'}: {formatLocalDateTime(selectedItem.last_confirmed_at)}</div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-lg bg-surface-accent dark:bg-gray-900/50 border border-default dark:border-gray-700 p-4">
          <div className="text-xs font-medium text-secondary dark:text-gray-400 mb-2">
            {t('claim' as any) || 'Claim'}
          </div>
          <p className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
            {selectedItem.claim}
          </p>
        </div>
        <div className="rounded-lg bg-surface-accent dark:bg-gray-900/50 border border-default dark:border-gray-700 p-4">
          <div className="text-xs font-medium text-secondary dark:text-gray-400 mb-2">
            {t('summary' as any) || 'Summary'}
          </div>
          <p className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
            {selectedItem.summary}
          </p>
        </div>
      </div>

      <GovernedMemoryTransitionSection
        t={t}
        selectedItem={selectedItem}
        evidenceCoverage={evidenceCoverage}
        transitionCues={transitionCues}
        transitionReason={transitionReason}
        actionError={actionError}
        actionLoading={actionLoading}
        supersedeDraftOpen={supersedeDraftOpen}
        successorDraftSuggestion={successorDraftSuggestion}
        primaryEvidence={primaryEvidence}
        successorTitle={successorTitle}
        successorClaim={successorClaim}
        successorSummary={successorSummary}
        verifyReasonSuggestion={verifyReasonSuggestion}
        staleReasonSuggestion={staleReasonSuggestion}
        supersedeReasonSuggestion={supersedeReasonSuggestion}
        onTransitionReasonChange={onTransitionReasonChange}
        onSupersedeDraftOpenChange={onSupersedeDraftOpenChange}
        onSuccessorTitleChange={onSuccessorTitleChange}
        onSuccessorClaimChange={onSuccessorClaimChange}
        onSuccessorSummaryChange={onSuccessorSummaryChange}
        onTransition={onTransition}
      />

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <GovernedMemoryVersionsSection t={t} versions={selectedDetail.versions} />
        <GovernedMemoryEvidenceSection
          t={t}
          evidence={selectedDetail.evidence}
          filteredEvidence={filteredEvidence}
          evidenceTypeCounts={evidenceTypeCounts}
          evidenceTypeFilter={evidenceTypeFilter}
          onEvidenceTypeFilterChange={onEvidenceTypeFilterChange}
        />
        <GovernedMemoryRelatedSections
          t={t}
          personalKnowledgeProjections={selectedDetail.personal_knowledge_projections}
          goalProjections={selectedDetail.goal_projections}
        />
      </div>

      <GovernedMemoryEdgesSection
        t={t}
        outgoingEdges={selectedDetail.outgoing_edges}
        onSelectMemoryItem={onSelectMemoryItem}
      />
    </div>
  );
}
