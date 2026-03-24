'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, Clock3, GitBranchPlus, RefreshCw } from 'lucide-react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { t } from '@/lib/i18n';
import { formatLocalDateTime } from '@/lib/time';
import { getApiBaseUrl } from '../../../../../lib/api-url';

interface WorkspaceMemoryItemSummary {
  id: string;
  kind: string;
  layer: string;
  title: string;
  claim: string;
  summary: string;
  lifecycle_status: string;
  verification_status: string;
  salience: number;
  confidence: number;
  subject_type: string;
  subject_id: string;
  supersedes_memory_id?: string | null;
  observed_at: string;
  last_confirmed_at?: string | null;
  created_at: string;
  updated_at: string;
}

interface WorkspaceMemoryListResponse {
  workspace_id: string;
  items: WorkspaceMemoryItemSummary[];
  total: number;
  limit: number;
}

interface MemoryVersionSummary {
  id: string;
  version_no: number;
  update_mode: string;
  claim_snapshot: string;
  summary_snapshot?: string | null;
  metadata_snapshot: Record<string, unknown>;
  created_at: string;
  created_from_run_id?: string | null;
}

interface MemoryEvidenceSummary {
  id: string;
  evidence_type: string;
  evidence_id: string;
  link_role: string;
  excerpt?: string | null;
  confidence?: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

interface MemoryEdgeSummary {
  id: string;
  from_memory_id: string;
  to_memory_id: string;
  edge_type: string;
  weight?: number | null;
  valid_from: string;
  valid_to?: string | null;
  evidence_strength?: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

interface PersonalKnowledgeProjectionSummary {
  id: string;
  knowledge_type: string;
  content: string;
  status: string;
  confidence: number;
  created_at: string;
  last_verified_at?: string | null;
}

interface GoalLedgerProjectionSummary {
  id: string;
  title: string;
  description: string;
  status: string;
  horizon: string;
  created_at: string;
  confirmed_at?: string | null;
}

interface WorkspaceMemoryDetailResponse {
  workspace_id: string;
  memory_item: WorkspaceMemoryItemSummary;
  versions: MemoryVersionSummary[];
  evidence: MemoryEvidenceSummary[];
  outgoing_edges: MemoryEdgeSummary[];
  personal_knowledge_projections: PersonalKnowledgeProjectionSummary[];
  goal_projections: GoalLedgerProjectionSummary[];
}

interface MemoryTransitionResponse {
  workspace_id: string;
  memory_item_id: string;
  transition: 'verify' | 'stale' | 'supersede';
  noop: boolean;
  lifecycle_status: string;
  verification_status: string;
  run_id: string;
  successor_memory_item_id?: string | null;
}

interface GovernedMemoryPanelProps {
  workspaceId: string;
}

function badgeClass(status: string): string {
  if (status === 'active' || status === 'verified') {
    return 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300';
  }
  if (status === 'candidate' || status === 'observed' || status === 'pending_confirmation') {
    return 'bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300';
  }
  if (status === 'stale' || status === 'challenged') {
    return 'bg-slate-200 dark:bg-slate-800 text-slate-800 dark:text-slate-300';
  }
  if (status === 'superseded' || status === 'deprecated') {
    return 'bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300';
  }
  return 'bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-300';
}

function prettyLabel(value: string): string {
  return value.replace(/_/g, ' ');
}

export function GovernedMemoryPanel({ workspaceId }: GovernedMemoryPanelProps) {
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
        throw new Error('Failed to load governed memory');
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
      setError(err instanceof Error ? err.message : 'Failed to load governed memory');
    } finally {
      setLoading(false);
    }
  }, [
    lifecycleStatus,
    queryMemoryId,
    selectedMemoryId,
    syncMemoryIdInUrl,
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
        throw new Error('Failed to load memory detail');
      }

      const data: WorkspaceMemoryDetailResponse = await response.json();
      setSelectedDetail(data);
      setSuccessorTitle('');
      setSuccessorClaim('');
      setSuccessorSummary('');
      setSupersedeDraftOpen(false);
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : 'Failed to load memory detail');
    } finally {
      setDetailLoading(false);
    }
  }, [workspaceId]);

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
    action: 'verify' | 'stale' | 'supersede',
    options?: {
      successor_title?: string;
      successor_claim?: string;
      successor_summary?: string;
    }
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
        throw new Error(data?.detail || 'Failed to apply memory transition');
      }

      const data: MemoryTransitionResponse = await response.json();
      const nextMemoryId = data.successor_memory_item_id || selectedMemoryId;
      await loadItems();
      await loadDetail(nextMemoryId);
      selectMemoryItem(nextMemoryId);
      setTransitionReason('');
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to apply memory transition');
    } finally {
      setActionLoading(false);
    }
  };

  const selectedItem = selectedDetail?.memory_item;

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
                onChange={(e) => setLifecycleStatus(e.target.value)}
                className="w-full sm:w-40 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              >
                <option value="">{t('all' as any) || 'All'}</option>
                <option value="candidate">candidate</option>
                <option value="active">active</option>
                <option value="stale">stale</option>
                <option value="superseded">superseded</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('verification' as any) || 'Verification'}
              </label>
              <select
                value={verificationStatus}
                onChange={(e) => setVerificationStatus(e.target.value)}
                className="w-full sm:w-40 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              >
                <option value="">{t('all' as any) || 'All'}</option>
                <option value="observed">observed</option>
                <option value="verified">verified</option>
                <option value="challenged">challenged</option>
              </select>
            </div>
            <button
              onClick={() => void loadItems()}
              className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
            >
              <RefreshCw size={14} />
              {t('refresh' as any) || 'Refresh'}
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <p className="text-sm text-red-800 dark:text-red-300">{error}</p>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[360px_minmax(0,1fr)] gap-4">
        <div className="space-y-2">
          {loading ? (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 text-center text-secondary dark:text-gray-400">
              {t('loading' as any) || 'Loading...'}
            </div>
          ) : items.length === 0 ? (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 text-center text-secondary dark:text-gray-400">
              {t('noGovernedMemory' as any) || 'No governed memory found for this workspace.'}
            </div>
          ) : (
            items.map((item) => (
              <button
                key={item.id}
                onClick={() => selectMemoryItem(item.id)}
                className={`w-full text-left rounded-lg border p-4 transition-colors ${
                  selectedMemoryId === item.id
                    ? 'border-blue-500 dark:border-blue-400 bg-blue-50 dark:bg-blue-900/20'
                    : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
              >
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <span className={`px-2 py-1 text-xs font-medium rounded ${badgeClass(item.lifecycle_status)}`}>
                    {item.lifecycle_status}
                  </span>
                  <span className={`px-2 py-1 text-xs font-medium rounded ${badgeClass(item.verification_status)}`}>
                    {item.verification_status}
                  </span>
                  <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
                    {prettyLabel(item.kind)}
                  </span>
                </div>
                <div className="text-sm font-semibold text-primary dark:text-gray-100 mb-1">
                  {item.title}
                </div>
                <div className="text-xs text-secondary dark:text-gray-400 mb-2">
                  {prettyLabel(item.layer)} · {formatLocalDateTime(item.observed_at)}
                </div>
                <p className="text-sm text-gray-700 dark:text-gray-300 line-clamp-3">
                  {item.summary || item.claim}
                </p>
              </button>
            ))
          )}
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-5">
          {detailLoading ? (
            <div className="text-center py-8 text-secondary dark:text-gray-400">
              {t('loading' as any) || 'Loading...'}
            </div>
          ) : detailError ? (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
              <p className="text-sm text-red-800 dark:text-red-300">{detailError}</p>
            </div>
          ) : !selectedDetail || !selectedItem ? (
            <div className="text-center py-8 text-secondary dark:text-gray-400">
              {t('selectMemoryItem' as any) || 'Select a memory item to inspect its detail.'}
            </div>
          ) : (
            <div className="space-y-5">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <div className="flex flex-wrap gap-2 mb-2">
                    <span className={`px-2 py-1 text-xs font-medium rounded ${badgeClass(selectedItem.lifecycle_status)}`}>
                      {selectedItem.lifecycle_status}
                    </span>
                    <span className={`px-2 py-1 text-xs font-medium rounded ${badgeClass(selectedItem.verification_status)}`}>
                      {selectedItem.verification_status}
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
                      onClick={() => selectMemoryItem(selectedItem.supersedes_memory_id || null)}
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

              <div className="rounded-lg border border-default dark:border-gray-700 p-4 space-y-3">
                <div className="text-sm font-semibold text-primary dark:text-gray-100">
                  {t('memoryTransitions' as any) || 'Memory Transitions'}
                </div>
                <textarea
                  value={transitionReason}
                  onChange={(e) => setTransitionReason(e.target.value)}
                  placeholder={t('transitionReasonPlaceholder' as any) || 'Optional reason for this transition'}
                  className="w-full min-h-[88px] px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                />
                {actionError && (
                  <div className="text-sm text-red-700 dark:text-red-300">{actionError}</div>
                )}
                <div className="flex flex-wrap gap-2">
                  {selectedItem.lifecycle_status === 'candidate' && (
                    <button
                      onClick={() => void handleTransition('verify')}
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
                        onClick={() => void handleTransition('stale')}
                        disabled={actionLoading}
                        className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded bg-slate-600 text-white hover:bg-slate-700 disabled:opacity-60"
                      >
                        <Clock3 size={14} />
                        {t('markStale' as any) || 'Mark Stale'}
                      </button>
                      <button
                        onClick={() => setSupersedeDraftOpen((value) => !value)}
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
                    <input
                      value={successorTitle}
                      onChange={(e) => setSuccessorTitle(e.target.value)}
                      placeholder={t('successorTitle' as any) || 'Successor title (optional)'}
                      className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    />
                    <textarea
                      value={successorClaim}
                      onChange={(e) => setSuccessorClaim(e.target.value)}
                      placeholder={t('successorClaim' as any) || 'Successor claim (optional)'}
                      className="w-full min-h-[88px] px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    />
                    <textarea
                      value={successorSummary}
                      onChange={(e) => setSuccessorSummary(e.target.value)}
                      placeholder={t('successorSummary' as any) || 'Successor summary (optional)'}
                      className="w-full min-h-[88px] px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    />
                    <div className="flex justify-end">
                      <button
                        onClick={() =>
                          void handleTransition('supersede', {
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

              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                <div className="rounded-lg border border-default dark:border-gray-700 p-4">
                  <div className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
                    {t('versions' as any) || 'Versions'}
                  </div>
                  <div className="space-y-3">
                    {selectedDetail.versions.length === 0 ? (
                      <div className="text-sm text-secondary dark:text-gray-400">
                        {t('noVersions' as any) || 'No versions recorded.'}
                      </div>
                    ) : (
                      selectedDetail.versions.map((version) => (
                        <div key={version.id} className="rounded bg-surface-accent dark:bg-gray-900/40 p-3">
                          <div className="flex items-center justify-between gap-3 mb-1">
                            <div className="text-xs font-medium text-primary dark:text-gray-100">
                              v{version.version_no}
                            </div>
                            <div className="text-xs text-secondary dark:text-gray-400">
                              {prettyLabel(version.update_mode)}
                            </div>
                          </div>
                          <div className="text-xs text-secondary dark:text-gray-400 mb-2">
                            {formatLocalDateTime(version.created_at)}
                          </div>
                          <div className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                            {version.summary_snapshot || version.claim_snapshot}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div className="rounded-lg border border-default dark:border-gray-700 p-4">
                  <div className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
                    {t('evidence' as any) || 'Evidence'}
                  </div>
                  <div className="space-y-3">
                    {selectedDetail.evidence.length === 0 ? (
                      <div className="text-sm text-secondary dark:text-gray-400">
                        {t('noEvidence' as any) || 'No evidence links recorded.'}
                      </div>
                    ) : (
                      selectedDetail.evidence.map((link) => (
                        <div key={link.id} className="rounded bg-surface-accent dark:bg-gray-900/40 p-3">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
                              {link.evidence_type}
                            </span>
                            <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
                              {link.link_role}
                            </span>
                          </div>
                          <div className="text-xs text-secondary dark:text-gray-400 mb-2 font-mono break-all">
                            {link.evidence_id}
                          </div>
                          {link.excerpt && (
                            <div className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                              {link.excerpt}
                            </div>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div className="rounded-lg border border-default dark:border-gray-700 p-4">
                  <div className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
                    {t('relatedKnowledge' as any) || 'Related Knowledge'}
                  </div>
                  <div className="space-y-3">
                    {selectedDetail.personal_knowledge_projections.length === 0 ? (
                      <div className="text-sm text-secondary dark:text-gray-400">
                        {t('noKnowledgeProjections' as any) || 'No personal knowledge projections.'}
                      </div>
                    ) : (
                      selectedDetail.personal_knowledge_projections.map((entry) => (
                        <div key={entry.id} className="rounded bg-surface-accent dark:bg-gray-900/40 p-3">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
                              {entry.knowledge_type}
                            </span>
                            <span className={`px-2 py-1 text-xs rounded ${badgeClass(entry.status)}`}>
                              {entry.status}
                            </span>
                          </div>
                          <div className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                            {entry.content}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div className="rounded-lg border border-default dark:border-gray-700 p-4">
                  <div className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
                    {t('relatedGoals' as any) || 'Related Goals'}
                  </div>
                  <div className="space-y-3">
                    {selectedDetail.goal_projections.length === 0 ? (
                      <div className="text-sm text-secondary dark:text-gray-400">
                        {t('noGoalProjections' as any) || 'No goal projections.'}
                      </div>
                    ) : (
                      selectedDetail.goal_projections.map((entry) => (
                        <div key={entry.id} className="rounded bg-surface-accent dark:bg-gray-900/40 p-3">
                          <div className="flex items-center gap-2 mb-1">
                            <span className={`px-2 py-1 text-xs rounded ${badgeClass(entry.status)}`}>
                              {entry.status}
                            </span>
                            <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
                              {entry.horizon}
                            </span>
                          </div>
                          <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                            {entry.title}
                          </div>
                          <div className="text-sm text-gray-700 dark:text-gray-300">
                            {entry.description}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>

              <div className="rounded-lg border border-default dark:border-gray-700 p-4">
                <div className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
                  {t('outgoingEdges' as any) || 'Outgoing Edges'}
                </div>
                <div className="space-y-3">
                  {selectedDetail.outgoing_edges.length === 0 ? (
                    <div className="text-sm text-secondary dark:text-gray-400">
                      {t('noOutgoingEdges' as any) || 'No outgoing edges recorded.'}
                    </div>
                  ) : (
                    selectedDetail.outgoing_edges.map((edge) => (
                      <div key={edge.id} className="rounded bg-surface-accent dark:bg-gray-900/40 p-3">
                        <div className="flex flex-wrap items-center gap-2 mb-1">
                          <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
                            {edge.edge_type}
                          </span>
                          <span className="text-xs text-secondary dark:text-gray-400">
                            {formatLocalDateTime(edge.created_at)}
                          </span>
                        </div>
                        <button
                          onClick={() => selectMemoryItem(edge.to_memory_id)}
                          className="text-xs text-blue-700 dark:text-blue-300 font-mono break-all hover:underline"
                        >
                          {edge.to_memory_id}
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
