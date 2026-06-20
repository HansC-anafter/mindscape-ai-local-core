'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useT } from '@/lib/i18n';

import { getApiBaseUrl } from '../../../../../lib/api-url';
import { GovernedMemoryPanelView } from './governedMemory/GovernedMemoryPanelView';
import {
  buildEvidenceCoverage,
  buildSuccessorDraftSuggestion,
  buildTransitionCues,
  buildTransitionReasonSuggestion,
  selectPrimaryEvidence,
} from './governedMemory/transitionModel';
import type {
  MemoryTransitionAction,
  MemoryTransitionOptions,
  MemoryTransitionResponse,
  WorkspaceMemoryDetailResponse,
  WorkspaceMemoryItemSummary,
  WorkspaceMemoryListResponse,
  GovernedMemoryPanelProps,
} from './governedMemory/types';

export function GovernedMemoryPanel({ workspaceId }: GovernedMemoryPanelProps) {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [items, setItems] = useState<WorkspaceMemoryItemSummary[]>([]);
  const [selectedMemoryId, setSelectedMemoryId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<WorkspaceMemoryDetailResponse | null>(null);
  const [lifecycleStatus, setLifecycleStatus] = useState<string>('');
  const [verificationStatus, setVerificationStatus] = useState<string>('');
  const [transitionReason, setTransitionReason] = useState('');
  const [supersedeDraftOpen, setSupersedeDraftOpen] = useState(false);
  const [successorTitle, setSuccessorTitle] = useState('');
  const [successorClaim, setSuccessorClaim] = useState('');
  const [successorSummary, setSuccessorSummary] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [evidenceTypeFilter, setEvidenceTypeFilter] = useState<string>('all');
  const queryMemoryId = searchParams?.get('memoryId') || null;

  const syncMemoryIdInUrl = useCallback((nextMemoryId: string | null) => {
    const nextParams = new URLSearchParams(searchParams?.toString() || '');
    if (nextMemoryId) {
      nextParams.set('memoryId', nextMemoryId);
    } else {
      nextParams.delete('memoryId');
    }
    const nextUrl = nextParams.toString() ? `${pathname}?${nextParams.toString()}` : pathname;
    router.replace(nextUrl, { scroll: false });
  }, [pathname, router, searchParams]);

  const selectMemoryItem = useCallback((nextMemoryId: string | null) => {
    setSelectedMemoryId(nextMemoryId);
    syncMemoryIdInUrl(nextMemoryId);
  }, [syncMemoryIdInUrl]);

  const loadItems = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const params = new URLSearchParams({ limit: '50' });
      if (lifecycleStatus) {
        params.append('lifecycle_status', lifecycleStatus);
      }
      if (verificationStatus) {
        params.append('verification_status', verificationStatus);
      }

      const apiUrl = getApiBaseUrl();
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/governance/memory?${params.toString()}`
      );
      if (!response.ok) {
        throw new Error(t('failedToLoadGovernedMemory'));
      }

      const data: WorkspaceMemoryListResponse = await response.json();
      setItems(data.items || []);
      const preferredMemoryId =
        (queryMemoryId && data.items.some((item) => item.id === queryMemoryId)
          ? queryMemoryId
          : null) ||
        (selectedMemoryId && data.items.some((item) => item.id === selectedMemoryId)
          ? selectedMemoryId
          : null) ||
        data.items[0]?.id ||
        null;

      if (preferredMemoryId !== selectedMemoryId) {
        setSelectedMemoryId(preferredMemoryId);
      }
      if (preferredMemoryId !== queryMemoryId) {
        syncMemoryIdInUrl(preferredMemoryId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('failedToLoadGovernedMemory'));
    } finally {
      setLoading(false);
    }
  }, [
    lifecycleStatus,
    queryMemoryId,
    selectedMemoryId,
    syncMemoryIdInUrl,
    t,
    verificationStatus,
    workspaceId,
  ]);

  const loadDetail = useCallback(async (memoryItemId: string) => {
    try {
      setDetailLoading(true);
      setDetailError(null);
      setActionError(null);

      const apiUrl = getApiBaseUrl();
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/governance/memory/${memoryItemId}`
      );
      if (!response.ok) {
        throw new Error(t('failedToLoadMemoryDetail'));
      }

      const data: WorkspaceMemoryDetailResponse = await response.json();
      setSelectedDetail(data);
      setEvidenceTypeFilter('all');
      setSuccessorTitle('');
      setSuccessorClaim('');
      setSuccessorSummary('');
      setSupersedeDraftOpen(false);
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : t('failedToLoadMemoryDetail'));
    } finally {
      setDetailLoading(false);
    }
  }, [t, workspaceId]);

  useEffect(() => {
    void loadItems();
  }, [loadItems]);

  useEffect(() => {
    if (!queryMemoryId || queryMemoryId === selectedMemoryId) {
      return;
    }
    setSelectedMemoryId(queryMemoryId);
  }, [queryMemoryId, selectedMemoryId]);

  useEffect(() => {
    if (!selectedMemoryId) {
      setSelectedDetail(null);
      return;
    }
    void loadDetail(selectedMemoryId);
  }, [loadDetail, selectedMemoryId]);

  const handleTransition = async (
    action: MemoryTransitionAction,
    options?: MemoryTransitionOptions
  ) => {
    if (!selectedMemoryId) {
      return;
    }

    try {
      setActionLoading(true);
      setActionError(null);

      const apiUrl = getApiBaseUrl();
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/governance/memory/${selectedMemoryId}/transition`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action,
            reason: transitionReason,
            ...options,
          }),
        }
      );

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail || t('failedToApplyMemoryTransition'));
      }

      const data: MemoryTransitionResponse = await response.json();
      const nextMemoryId = data.successor_memory_item_id || selectedMemoryId;
      await loadItems();
      await loadDetail(nextMemoryId);
      selectMemoryItem(nextMemoryId);
      setTransitionReason('');
    } catch (err) {
      setActionError(err instanceof Error ? err.message : t('failedToApplyMemoryTransition'));
    } finally {
      setActionLoading(false);
    }
  };

  const selectedItem = selectedDetail?.memory_item;
  const evidenceTypeCounts = (selectedDetail?.evidence || []).reduce<Record<string, number>>(
    (acc, link) => {
      acc[link.evidence_type] = (acc[link.evidence_type] || 0) + 1;
      return acc;
    },
    {}
  );
  const filteredEvidence = (selectedDetail?.evidence || [])
    .filter((link) => evidenceTypeFilter === 'all' || link.evidence_type === evidenceTypeFilter)
    .sort((a, b) => {
      const sortWeight = (evidenceType: string): number => {
        if (evidenceType === 'session_digest') return 0;
        if (evidenceType === 'meeting_decision') return 1;
        if (evidenceType === 'task_execution') return 2;
        if (evidenceType === 'execution_trace') return 3;
        if (evidenceType === 'artifact_result') return 4;
        if (evidenceType === 'governance_decision') return 5;
        if (evidenceType === 'lens_patch') return 6;
        if (evidenceType === 'intent_log') return 7;
        if (evidenceType === 'reasoning_trace') return 8;
        if (evidenceType === 'lens_receipt') return 9;
        if (evidenceType === 'writeback_receipt') return 10;
        return 10;
      };
      const weightDiff = sortWeight(a.evidence_type) - sortWeight(b.evidence_type);
      if (weightDiff !== 0) {
        return weightDiff;
      }
      return a.created_at.localeCompare(b.created_at);
    });
  const evidenceCoverage =
    selectedDetail?.evidence_coverage || buildEvidenceCoverage(selectedDetail?.evidence || []);
  const primaryEvidence = selectPrimaryEvidence(selectedDetail?.evidence || []);
  const transitionCues =
    selectedDetail?.transition_cues ||
    (selectedItem
      ? buildTransitionCues(selectedItem, selectedDetail?.evidence || [], evidenceCoverage, t)
      : []);
  const successorDraftSuggestion =
    selectedDetail?.successor_draft_suggestion ||
    (selectedItem && selectedItem.lifecycle_status === 'active'
      ? buildSuccessorDraftSuggestion(selectedItem, selectedDetail?.evidence || [], evidenceCoverage, t)
      : null);
  const verifyReasonSuggestion =
    selectedDetail?.transition_reason_suggestions?.verify ||
    (selectedItem
      ? buildTransitionReasonSuggestion('verify', selectedItem, primaryEvidence, evidenceCoverage, t)
      : '');
  const staleReasonSuggestion =
    selectedDetail?.transition_reason_suggestions?.stale ||
    (selectedItem
      ? buildTransitionReasonSuggestion('stale', selectedItem, primaryEvidence, evidenceCoverage, t)
      : '');
  const supersedeReasonSuggestion =
    selectedDetail?.transition_reason_suggestions?.supersede ||
    (selectedItem
      ? buildTransitionReasonSuggestion('supersede', selectedItem, primaryEvidence, evidenceCoverage, t)
      : '');

  useEffect(() => {
    if (!supersedeDraftOpen || !successorDraftSuggestion) {
      return;
    }
    if (successorTitle || successorClaim || successorSummary) {
      return;
    }
    setSuccessorTitle(successorDraftSuggestion.title);
    setSuccessorClaim(successorDraftSuggestion.claim);
    setSuccessorSummary(successorDraftSuggestion.summary);
  }, [
    successorClaim,
    successorDraftSuggestion,
    successorSummary,
    successorTitle,
    supersedeDraftOpen,
  ]);

  return (
    <GovernedMemoryPanelView
      t={t}
      workspaceId={workspaceId}
      apiUrl={getApiBaseUrl()}
      loading={loading}
      detailLoading={detailLoading}
      error={error}
      detailError={detailError}
      items={items}
      selectedMemoryId={selectedMemoryId}
      selectedDetail={selectedDetail}
      selectedItem={selectedItem}
      lifecycleStatus={lifecycleStatus}
      verificationStatus={verificationStatus}
      transitionReason={transitionReason}
      supersedeDraftOpen={supersedeDraftOpen}
      successorTitle={successorTitle}
      successorClaim={successorClaim}
      successorSummary={successorSummary}
      actionError={actionError}
      actionLoading={actionLoading}
      evidenceTypeFilter={evidenceTypeFilter}
      evidenceTypeCounts={evidenceTypeCounts}
      filteredEvidence={filteredEvidence}
      evidenceCoverage={evidenceCoverage}
      primaryEvidence={primaryEvidence}
      transitionCues={transitionCues}
      successorDraftSuggestion={successorDraftSuggestion}
      verifyReasonSuggestion={verifyReasonSuggestion}
      staleReasonSuggestion={staleReasonSuggestion}
      supersedeReasonSuggestion={supersedeReasonSuggestion}
      onLifecycleStatusChange={setLifecycleStatus}
      onVerificationStatusChange={setVerificationStatus}
      onRefresh={() => void loadItems()}
      onSelectMemoryItem={selectMemoryItem}
      onTransitionReasonChange={setTransitionReason}
      onSupersedeDraftOpenChange={setSupersedeDraftOpen}
      onSuccessorTitleChange={setSuccessorTitle}
      onSuccessorClaimChange={setSuccessorClaim}
      onSuccessorSummaryChange={setSuccessorSummary}
      onEvidenceTypeFilterChange={setEvidenceTypeFilter}
      onTransition={handleTransition}
    />
  );
}
