import React, { useState as useStateReact, useEffect, useCallback, useMemo, useRef } from 'react';
import { AlertCircle, ArrowLeft, ExternalLink, Sprout, Tag, FileText, Brain, Network, Grid3X3, Loader2, Heart, MessageCircle, Mail, Phone, MapPin, Instagram, Youtube } from 'lucide-react';

import type { ConnectedAccount, DiscoveredAccount } from '../types';
import type { SeedInfo, PostAnalysis, LatestBatchPinSummaryResponse, PinFailedAttempt } from '../insightsApi';
import {
  formatCount,
  getProxiedImageUrl,
  getAvatarUrl,
  getPostThumbnailUrl,
  getReferenceImageUrl,
  parseCountTextToNumber,
} from '../utils';
import { createInsightsApi } from '../insightsApi';
import { ProfileTagsPanel } from './insights/ProfileTagsPanel';
import { ContentAnalysisPanel } from './insights/ContentAnalysisPanel';
import { NetworkGraphPanel } from './insights/NetworkGraphPanel';
import { PersonaPanel } from './insights/PersonaPanel';
import { useIGWorkspaceEvents } from '../../../hooks/useIGWorkspaceEvents';
import { useExecutionPolling } from '@/hooks/useExecutionPolling';

type AccountReferenceEntry = {
  reference_id: string;
  source_shortcode?: string | null;
  analysis_status?: string | null;
};

type AccountReferencesResponse = {
  references?: AccountReferenceEntry[];
  has_more?: boolean;
};

type AggregatedReferenceStatus = 'PINNED' | 'PENDING' | 'COMPLETED' | 'FAILED';

type AggregatedReferencePostState = {
  status: AggregatedReferenceStatus;
  primaryReferenceId: string | null;
  totalReferences: number;
  completedReferences: number;
  pendingReferences: number;
  failedReferences: number;
  pinnedOnlyReferences: number;
};

type AccountReferenceSummary = {
  totalReferences: number;
  pinnedPosts: number;
  completedPosts: number;
  pendingPosts: number;
  failedPosts: number;
  pinnedOnlyPosts: number;
  byShortcode: Record<string, AggregatedReferencePostState>;
};

const EMPTY_REFERENCE_SUMMARY: AccountReferenceSummary = {
  totalReferences: 0,
  pinnedPosts: 0,
  completedPosts: 0,
  pendingPosts: 0,
  failedPosts: 0,
  pinnedOnlyPosts: 0,
  byShortcode: {},
};

const ACCOUNT_POSTS_PAGE_LIMIT = 500;
const ACCOUNT_REFERENCES_PAGE_LIMIT = 200;

function normalizeReferenceShortcode(shortcode: string | null | undefined): string {
  return (shortcode || '').toString().trim().replace(/_c\d+$/i, '');
}

function buildAccountReferenceSummary(references: AccountReferenceEntry[]): AccountReferenceSummary {
  if (!Array.isArray(references) || references.length === 0) {
    return EMPTY_REFERENCE_SUMMARY;
  }

  const byShortcode: Record<string, AggregatedReferencePostState> = {};

  references.forEach((reference) => {
    const shortcode = normalizeReferenceShortcode(reference.source_shortcode);
    if (!shortcode) return;

    if (!byShortcode[shortcode]) {
      byShortcode[shortcode] = {
        status: 'PINNED',
        primaryReferenceId: reference.reference_id || null,
        totalReferences: 0,
        completedReferences: 0,
        pendingReferences: 0,
        failedReferences: 0,
        pinnedOnlyReferences: 0,
      };
    }

    const entry = byShortcode[shortcode];
    if (!entry.primaryReferenceId && reference.reference_id) {
      entry.primaryReferenceId = reference.reference_id;
    }
    const status = (reference.analysis_status || '').toString().trim().toUpperCase();

    entry.totalReferences += 1;
    if (status === 'COMPLETED') {
      entry.completedReferences += 1;
    } else if (['PENDING', 'RUNNING', 'QUEUED', 'PAUSED'].includes(status)) {
      entry.pendingReferences += 1;
    } else if (status === 'FAILED') {
      entry.failedReferences += 1;
    } else {
      entry.pinnedOnlyReferences += 1;
    }
  });

  let completedPosts = 0;
  let pendingPosts = 0;
  let failedPosts = 0;
  let pinnedOnlyPosts = 0;

  Object.values(byShortcode).forEach((entry) => {
    if (entry.completedReferences > 0) {
      entry.status = 'COMPLETED';
      completedPosts += 1;
      return;
    }
    if (entry.pendingReferences > 0) {
      entry.status = 'PENDING';
      pendingPosts += 1;
      return;
    }
    if (entry.failedReferences > 0) {
      entry.status = 'FAILED';
      failedPosts += 1;
      return;
    }
    entry.status = 'PINNED';
    pinnedOnlyPosts += 1;
  });

  return {
    totalReferences: references.length,
    pinnedPosts: Object.keys(byShortcode).length,
    completedPosts,
    pendingPosts,
    failedPosts,
    pinnedOnlyPosts,
    byShortcode,
  };
}

function getReferenceStatusBadge(status: AggregatedReferenceStatus): { label: string; className: string } {
  switch (status) {
    case 'COMPLETED':
      return {
        label: 'Analyzed',
        className: 'bg-emerald-500/90 text-white',
      };
    case 'PENDING':
      return {
        label: 'Pending',
        className: 'bg-blue-500/90 text-white',
      };
    case 'FAILED':
      return {
        label: 'Failed',
        className: 'bg-rose-500/90 text-white',
      };
    default:
      return {
        label: 'Pinned',
        className: 'bg-gray-900/75 text-white',
      };
  }
}

function getBatchPinStatusMeta(status: string | null | undefined): { label: string; className: string } {
  switch ((status || '').toString().trim().toLowerCase()) {
    case 'running':
      return { label: 'Running', className: 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300' };
    case 'pending':
    case 'queued':
    case 'paused':
      return { label: 'Queued', className: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300' };
    case 'succeeded':
    case 'completed':
      return { label: 'Completed', className: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300' };
    case 'failed':
      return { label: 'Failed', className: 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-300' };
    default:
      return { label: (status || 'Unknown').toString(), className: 'border-gray-200 bg-gray-50 text-gray-700 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300' };
  }
}

function getProfileNameFromUserDataDir(userDataDir: string | null | undefined): string | null {
  const trimmed = (userDataDir || '').toString().trim();
  if (!trimmed) return null;
  const segments = trimmed.split('/').filter(Boolean);
  return segments[segments.length - 1] || trimmed;
}

type RunPlaybookResult = {
  success: boolean;
  execution_id?: string;
  error?: string;
};

type RunPlaybookFn = (
  playbookCode: string,
  params: Record<string, unknown>
) => Promise<RunPlaybookResult | void> | RunPlaybookResult | void;

export function AccountDetailPanel(props: {
  apiUrl: string;
  workspaceId: string;
  selectedAccount: ConnectedAccount | DiscoveredAccount;
  onBack: () => void;

  snapshots: any[];
  snapshotsLoading: boolean;
  snapshotError: string | null;
  snapshotCompareIds: string[];
  onSnapshotCompareIdsChange: (ids: string[]) => void;
  onCaptureSnapshot: (handle: string) => void;

  newTagInput: string;
  onNewTagInputChange: (value: string) => void;
  setTagsForHandle: (handle: string, tags: string[]) => void;
  getTagsForHandle: (handle: string, fallbackTags?: string[]) => string[];
  onAddToSeed?: (handle: string) => Promise<void>;

  /** Seed-level detail mode */
  seed?: string;
  allSeeds?: SeedInfo[];
  onRunPlaybook?: RunPlaybookFn;
}) {
  const {
    apiUrl,
    selectedAccount,
    onBack,
    snapshots,
    snapshotsLoading,
    snapshotError,
    snapshotCompareIds,
    onSnapshotCompareIdsChange,
    onCaptureSnapshot,
    newTagInput,
    onNewTagInputChange,
    setTagsForHandle,
    getTagsForHandle,
    onAddToSeed,
  } = props;

  const isConnected = 'channel_config_id' in selectedAccount;
  const selectedHandle = !isConnected ? (selectedAccount as DiscoveredAccount).handle : null;
  const latestSnapshot = snapshots.length > 0 ? snapshots[0] : null;
  const latestSnapshotContent = latestSnapshot ? (latestSnapshot.content?.content || latestSnapshot.content || {}) : null;
  const latestProfile = latestSnapshotContent ? latestSnapshotContent.profile : null;
  const [seedAddState, setSeedAddState] = useStateReact<'idle' | 'adding' | 'added' | 'failed'>('idle');
  const [activeInsightTab, setActiveInsightTab] = useStateReact<'tags' | 'content' | 'network' | 'persona' | 'posts' | null>(null);

  // Check if account is already a seed
  const isAlreadySeed = !!(selectedHandle && props.allSeeds?.some(
    (s) => s.seed === selectedHandle
  ));

  useEffect(() => {
    setSeedAddState('idle');
  }, [selectedHandle]);

  // Post Grid state
  const [gridPosts, setGridPosts] = useStateReact<PostAnalysis[]>([]);
  const [gridLoading, setGridLoading] = useStateReact(false);
  const [failedGridThumbnails, setFailedGridThumbnails] = useStateReact<Record<string, true>>({});
  const [accountReferences, setAccountReferences] = useStateReact<AccountReferenceEntry[]>([]);
  const [batchPinSummary, setBatchPinSummary] = useStateReact<LatestBatchPinSummaryResponse | null>(null);
  const [pinFailedAttempts, setPinFailedAttempts] = useStateReact<PinFailedAttempt[]>([]);
  const [pinFailedAttemptsTotal, setPinFailedAttemptsTotal] = useStateReact(0);
  const [retryingPinFailures, setRetryingPinFailures] = useStateReact(false);

  const isSeedMode = !!props.seed;
  const detailHandle = props.seed || selectedHandle || null;

  // Build insight tabs dynamically
  const INSIGHT_TABS: { key: 'tags' | 'content' | 'network' | 'persona' | 'posts'; label: string; icon: any }[] = [
    { key: 'tags', label: 'Tags', icon: Tag },
    { key: 'content', label: 'Feed', icon: FileText },
    ...(isSeedMode ? [{ key: 'network' as const, label: 'Network', icon: Network }] : []),
    { key: 'persona', label: 'Persona', icon: Brain },
    { key: 'posts', label: 'Posts', icon: Grid3X3 },
  ];

  const [pinningPostId, setPinningPostId] = useStateReact<string | null>(null);
  const [batchCount, setBatchCount] = useStateReact<string>('');
  const [activeBatchPinExecutionId, setActiveBatchPinExecutionId] = useStateReact<string | null>(null);
  const postsTabLoadInFlightRef = useRef<Promise<void> | null>(null);
  const batchSummaryLoadInFlightRef = useRef<Promise<void> | null>(null);

  const referenceSummary = useMemo(
    () => buildAccountReferenceSummary(accountReferences),
    [accountReferences],
  );
  const latestBatchAttempt = batchPinSummary?.latest_attempt ?? null;
  const latestCompletedBatch = batchPinSummary?.latest_completed ?? null;
  const latestBatchMetrics = latestCompletedBatch?.metrics ?? latestBatchAttempt?.metrics ?? null;
  const latestBatchTarget = latestBatchAttempt?.target_count ?? latestCompletedBatch?.target_count ?? null;
  const currentReferenceCount = referenceSummary.totalReferences;
  const remainingBatchTarget = latestBatchTarget !== null && latestBatchTarget !== undefined
    ? Math.max(latestBatchTarget - currentReferenceCount, 0)
    : (latestBatchMetrics?.remaining_to_target ?? null);
  const latestBatchProfileName = getProfileNameFromUserDataDir(
    latestBatchAttempt?.user_data_dir ?? latestCompletedBatch?.user_data_dir ?? null,
  );
  const latestBatchStatusMeta = getBatchPinStatusMeta(latestBatchAttempt?.status ?? latestCompletedBatch?.status);
  const pinnedPostIds = useMemo(
    () => new Set(Object.keys(referenceSummary.byShortcode)),
    [referenceSummary],
  );

  const loadLatestBatchPinSummary = useCallback(async () => {
    if (!detailHandle) {
      setBatchPinSummary(null);
      return;
    }

    if (batchSummaryLoadInFlightRef.current) {
      return batchSummaryLoadInFlightRef.current;
    }

    const request = (async () => {
      const api = createInsightsApi(apiUrl);
      const latestBatchData = await api.fetchLatestBatchPinSummary(props.workspaceId, detailHandle).catch(
        () => ({ latest_attempt: null, latest_completed: null }),
      );
      setBatchPinSummary(latestBatchData);
    })().finally(() => {
      batchSummaryLoadInFlightRef.current = null;
    });

    batchSummaryLoadInFlightRef.current = request;
    return request;
  }, [apiUrl, detailHandle, props.workspaceId, setBatchPinSummary]);

  const loadPostsTabData = useCallback(async () => {
    if (postsTabLoadInFlightRef.current) {
      return postsTabLoadInFlightRef.current;
    }

    if (!detailHandle) {
      setGridPosts([]);
      setAccountReferences([]);
      setBatchPinSummary(null);
      setPinFailedAttempts([]);
      setPinFailedAttemptsTotal(0);
      return;
    }

    const request = (async () => {
      const api = createInsightsApi(apiUrl);
      const loadAllAccountReferences = async (): Promise<AccountReferenceEntry[]> => {
        const collected: AccountReferenceEntry[] = [];
        let offset = 0;

        while (true) {
          const qs = new URLSearchParams({
            workspace_id: props.workspaceId,
            source_handle: detailHandle,
            limit: String(ACCOUNT_REFERENCES_PAGE_LIMIT),
            offset: String(offset),
          });

          const refsPage: AccountReferencesResponse = await fetch(`${apiUrl}/api/v1/ig/references/?${qs.toString()}`)
            .then((response) => (response.ok ? response.json() : { references: [], has_more: false }))
            .catch(() => ({ references: [], has_more: false }));

          const pageReferences = Array.isArray(refsPage.references) ? refsPage.references : [];
          collected.push(...pageReferences);

          if (!refsPage.has_more || pageReferences.length === 0) {
            break;
          }

          offset += pageReferences.length;
        }

        return collected;
      };

      const [postsData, refsData, latestBatchData, pinFailedData] = await Promise.all([
        api.fetchPosts(props.workspaceId, undefined, {
          handle: detailHandle,
          limit: ACCOUNT_POSTS_PAGE_LIMIT,
        }),
        loadAllAccountReferences(),
        api.fetchLatestBatchPinSummary(props.workspaceId, detailHandle).catch(
          () => ({ latest_attempt: null, latest_completed: null }),
        ),
        api.fetchPinFailedAttempts(props.workspaceId, detailHandle, 'pending_retry', 50).catch(
          () => ({ attempts: [], total: 0 }),
        ),
      ]);

      setGridPosts(postsData);
      setAccountReferences(refsData);
      setBatchPinSummary(latestBatchData);
      setPinFailedAttempts(pinFailedData.attempts || []);
      setPinFailedAttemptsTotal(pinFailedData.total || 0);
    })().finally(() => {
      postsTabLoadInFlightRef.current = null;
    });

    postsTabLoadInFlightRef.current = request;
    return request;
  }, [apiUrl, detailHandle, props.workspaceId, setAccountReferences, setBatchPinSummary, setGridPosts]);

  useIGWorkspaceEvents({
    workspaceId: props.workspaceId,
    apiUrl,
    onEvent: (_event, metadata) => {
      if ((metadata.playbookCode || '').toString() !== 'ig_batch_pin_references') return;
      const execId = (metadata.executionId || '').toString().trim();
      if (!execId || !detailHandle) return;

      const targetHandle = (
        metadata.targetHandle ||
        metadata.targetUsername ||
        ''
      ).toString().replace(/^@/, '').trim().toLowerCase();
      const normalizedDetailHandle = detailHandle.replace(/^@/, '').trim().toLowerCase();
      if (!targetHandle || targetHandle !== normalizedDetailHandle) return;

      const lifecycleState = (metadata.lifecycleState || '').toString().toUpperCase();
      if (!['READY', 'RUNNING', 'PENDING', 'QUEUED', 'PAUSED'].includes(lifecycleState)) return;

      setActiveBatchPinExecutionId((prev) => (prev === execId ? prev : execId));
      void loadLatestBatchPinSummary();
      if (activeInsightTab === 'posts') {
        setGridLoading(true);
        void loadPostsTabData().finally(() => setGridLoading(false));
      }
    },
  });

  useExecutionPolling({
    executionId: activeInsightTab === 'posts' ? activeBatchPinExecutionId : null,
    workspaceId: props.workspaceId,
    apiUrl,
    onUpdate: (event) => {
      const eventType = (event?.type || '').toString().toLowerCase();
      const streamEndReason = (event?.reason || event?.data?.reason || '').toString().toLowerCase();
      const streamEndTerminal =
        event?.terminal === true || event?.data?.terminal === true;
      const isTerminalStreamEnd =
        eventType === 'stream_end' &&
        (streamEndTerminal ||
          streamEndReason === 'terminal' ||
          streamEndReason === 'completed' ||
          streamEndReason === 'failed' ||
          streamEndReason === 'not_found');

      if (
        eventType === 'execution_complete' ||
        eventType === 'execution_completed' ||
        eventType === 'execution_error' ||
        isTerminalStreamEnd
      ) {
        setActiveBatchPinExecutionId(null);
        void loadPostsTabData();
      }
    },
    pollIntervalMs: 10_000,
    enableSSE: true,
    enablePollingFallback: true,
    sseDebounceMs: 1_200,
    pollFn: loadLatestBatchPinSummary,
  });

  // Load posts for grid when posts tab is active
  useEffect(() => {
    if (activeInsightTab !== 'posts') return;
    setGridLoading(true);
    setFailedGridThumbnails({});
    void loadPostsTabData()
      .catch(console.error)
      .finally(() => setGridLoading(false));
  }, [activeInsightTab, loadPostsTabData, setFailedGridThumbnails, setGridLoading]);

  // Load all seeds for NetworkGraphPanel when in seed mode
  const [internalSeeds, setInternalSeeds] = useStateReact<SeedInfo[]>([]);
  useEffect(() => {
    if (!isSeedMode) return;
    const api = createInsightsApi(apiUrl);
    api.fetchSeeds(props.workspaceId).then(setInternalSeeds).catch(console.error);
  }, [apiUrl, isSeedMode, props.workspaceId, setInternalSeeds]);

  const resolvedAllSeeds = (props.allSeeds && props.allSeeds.length > 0) ? props.allSeeds : internalSeeds;

  const togglePin = async (post: PostAnalysis) => {
    const normalizedShortcode = normalizeReferenceShortcode(post.post_shortcode);
    if (!post.thumbnail_url || !normalizedShortcode || !detailHandle) return;
    setPinningPostId(post.post_shortcode);
    try {
      const matchingReferences = accountReferences.filter(
        (reference) => normalizeReferenceShortcode(reference.source_shortcode) === normalizedShortcode
      );
      const isPinned = matchingReferences.length > 0;
      if (isPinned) {
        await Promise.all(
          matchingReferences
            .map((reference) => reference.reference_id)
            .filter(Boolean)
            .map((referenceId) =>
              fetch(
                `${apiUrl}/api/v1/ig/references/${referenceId}?workspace_id=${props.workspaceId}`,
                { method: 'DELETE' }
              )
            )
        );
      } else {
        const response = await fetch(`${apiUrl}/api/v1/ig/references/pin`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(
            {
              workspace_id: props.workspaceId,
              image_url: post.thumbnail_url,
              source_handle: detailHandle,
              source_url: post.post_url,
              source_shortcode: post.post_shortcode,
              tags: ['manual_pin'],
            },
          ),
        });
        if (!response.ok) {
          throw new Error(`Pin failed: ${response.status}`);
        }
      }
      await loadPostsTabData();
    } catch (e) {
      console.error('Failed to toggle pin:', e);
    } finally {
      setPinningPostId(null);
    }
  };

  const handleBatchPin = async (count: number) => {
    if (!props.onRunPlaybook || !detailHandle) return;

    try {
      const result = await Promise.resolve(
        props.onRunPlaybook('ig_batch_pin_references', {
          target_handle: detailHandle,
          target_count: count,
        }),
      );
      const executionId =
        result && typeof result === 'object' && 'execution_id' in result
          ? (result.execution_id || '').toString().trim()
          : '';
      if (executionId) {
        setActiveBatchPinExecutionId((prev) => (prev === executionId ? prev : executionId));
      }
    } catch (error) {
      console.error('Failed to start batch pin:', error);
    } finally {
      if (activeInsightTab === 'posts') {
        setGridLoading(true);
        void loadPostsTabData().finally(() => setGridLoading(false));
      } else {
        void loadLatestBatchPinSummary();
      }
    }
  };

  const handleRetryPinFailures = useCallback(async () => {
    if (!detailHandle || retryingPinFailures) return;
    setRetryingPinFailures(true);
    try {
      const api = createInsightsApi(apiUrl);
      await api.retryPinFailedAttempts(props.workspaceId, {
        handle: detailHandle,
        limit: 50,
        pinned_by: 'account_detail_retry_failed_pins',
      });
      await loadPostsTabData();
    } catch (error) {
      console.error('Failed to retry failed pins:', error);
    } finally {
      setRetryingPinFailures(false);
    }
  }, [apiUrl, detailHandle, loadPostsTabData, props.workspaceId, retryingPinFailures]);

  return (
    <div className="h-full flex flex-col p-4">
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={onBack}
          className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 flex items-center gap-2"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Account List
        </button>
        {!isConnected && selectedHandle && onAddToSeed && (
          <button
            onClick={async () => {
              if (isAlreadySeed || seedAddState === 'adding' || seedAddState === 'added') {
                return;
              }
              setSeedAddState('adding');
              try {
                await onAddToSeed(selectedHandle);
                setSeedAddState('added');
              } catch (_error) {
                setSeedAddState('failed');
              }
            }}
            disabled={seedAddState === 'adding' || isAlreadySeed}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${isAlreadySeed
              ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 cursor-default'
              : seedAddState === 'added'
                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
              : seedAddState === 'failed'
                ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 hover:bg-red-200 dark:hover:bg-red-900/40'
              : seedAddState === 'adding'
                ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300 cursor-wait'
                : 'bg-purple-50 text-purple-600 dark:bg-purple-900/30 dark:text-purple-400 hover:bg-purple-100 dark:hover:bg-purple-900/50'
              }`}
          >
            {seedAddState === 'adding' ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : seedAddState === 'failed' ? (
              <AlertCircle className="w-3.5 h-3.5" />
            ) : (
              <Sprout className="w-3.5 h-3.5" />
            )}
            {isAlreadySeed
              ? 'Already a Seed'
              : seedAddState === 'adding'
                ? 'Adding to Seeds...'
              : seedAddState === 'added'
                ? 'Added to Seeds'
              : seedAddState === 'failed'
                ? 'Retry Add to Seeds'
              : 'Add to Seeds'}
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto space-y-4">
        {isConnected ? (
          <>
            <div>
              <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-2">
                {(selectedAccount as ConnectedAccount).channel_name}
              </h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {(selectedAccount as ConnectedAccount).username || 'N/A'}
              </p>
            </div>

            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
                Connection Status
              </h3>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-700 dark:text-gray-300">Status</span>
                  <span className={`px-2 py-1 text-xs rounded ${(selectedAccount as ConnectedAccount).status === 'connected'
                    ? 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400'
                    : (selectedAccount as ConnectedAccount).status === 'expired'
                      ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400'
                      : 'bg-red-100 text-red-800 dark:bg-red-900/20 dark:text-red-400'
                    }`}>
                    {(selectedAccount as ConnectedAccount).status === 'connected' ? 'Connected' :
                      (selectedAccount as ConnectedAccount).status === 'expired' ? 'Expired' :
                        'Insufficient Permissions'}
                  </span>
                </div>
                {(selectedAccount as ConnectedAccount).expires_at && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-700 dark:text-gray-300">Expires At</span>
                    <span className="text-sm text-gray-900 dark:text-gray-100">
                      {new Date((selectedAccount as ConnectedAccount).expires_at!).toLocaleString()}
                    </span>
                  </div>
                )}
                {(selectedAccount as ConnectedAccount).page_id && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-700 dark:text-gray-300">Page ID</span>
                    <span className="text-sm text-gray-900 dark:text-gray-100">
                      {(selectedAccount as ConnectedAccount).page_id}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {(selectedAccount as ConnectedAccount).permissions.length > 0 && (
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
                  Available Permissions
                </h3>
                <div className="flex flex-wrap gap-2">
                  {(selectedAccount as ConnectedAccount).permissions.map((perm, index) => (
                    <span
                      key={index}
                      className="px-2 py-1 text-xs bg-blue-100 dark:bg-blue-900/20 text-blue-800 dark:text-blue-400 rounded"
                    >
                      {perm === 'publish' ? 'Publish' :
                        perm === 'schedule' ? 'Schedule' :
                          perm === 'insights' ? 'Insights' :
                            perm}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {(selectedAccount as ConnectedAccount).status !== 'connected' && (selectedAccount as ConnectedAccount).reauth_url && (
              <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
                <div className="flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 text-yellow-600 dark:text-yellow-400 mt-0.5" />
                  <div className="flex-1">
                    <p className="text-sm font-semibold text-yellow-900 dark:text-yellow-100 mb-1">
                      Reauthorization Required
                    </p>
                    <a
                      href={(selectedAccount as ConnectedAccount).reauth_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-yellow-700 dark:text-yellow-300 hover:underline flex items-center gap-1"
                    >
                      Click to reauthorize <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                </div>
              </div>
            )}
          </>
        ) : (
          <>
            <div className="flex items-center gap-3 flex-wrap">
              <img
                src={
                  getProxiedImageUrl('', (selectedAccount as DiscoveredAccount).profile_picture_url)
                  || getAvatarUrl((selectedAccount as DiscoveredAccount).handle, (selectedAccount as DiscoveredAccount).fetched_at)
                }
                alt={(selectedAccount as DiscoveredAccount).handle}
                className="w-12 h-12 rounded-full object-cover"
                onError={(e: any) => {
                  const fb = getAvatarUrl((selectedAccount as DiscoveredAccount).handle, (selectedAccount as DiscoveredAccount).fetched_at);
                  if (e.target.src !== fb) e.target.src = fb;
                }}
              />
              <div className="mr-auto">
                <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100 leading-tight">
                  @{(selectedAccount as DiscoveredAccount).handle}
                  {(latestProfile?.is_verified || (selectedAccount as DiscoveredAccount).is_verified) && (
                    <span className="ml-1 text-xs text-blue-500">✓</span>
                  )}
                </h2>
                {(selectedAccount as DiscoveredAccount).name && (
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {(selectedAccount as DiscoveredAccount).name}
                  </p>
                )}
              </div>
              {/* ── Insight Tabs (inline with header) ── */}
              <div className="flex items-center gap-1.5">
                {INSIGHT_TABS.map((tab) => (
                  <button
                    key={tab.key}
                    onClick={() => setActiveInsightTab(activeInsightTab === tab.key ? null : tab.key)}
                    className={`flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-full transition-colors ${activeInsightTab === tab.key
                      ? 'bg-blue-500 text-white'
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
                      }`}
                  >
                    <tab.icon className="w-3 h-3" />
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>

            {/* ── Insight content (when a tab is selected) ── */}
            {activeInsightTab && (
              <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700" style={{ minHeight: '400px' }}>
                {activeInsightTab === 'tags' && (
                  <ProfileTagsPanel
                    workspaceId={props.workspaceId}
                    apiUrl={apiUrl}
                    seed={props.seed || undefined}
                    handle={(!props.seed && selectedHandle) ? selectedHandle : undefined}
                    onRunPlaybook={props.onRunPlaybook}
                  />
                )}
                {activeInsightTab === 'content' && (
                  <ContentAnalysisPanel
                    workspaceId={props.workspaceId}
                    apiUrl={apiUrl}
                    seed={props.seed || undefined}
                    handle={(!props.seed && selectedHandle) ? selectedHandle : undefined}
                    onRunPlaybook={props.onRunPlaybook}
                  />
                )}
                {activeInsightTab === 'network' && props.seed && (
                  <NetworkGraphPanel
                    workspaceId={props.workspaceId}
                    apiUrl={apiUrl}
                    seed={props.seed}
                    allSeeds={resolvedAllSeeds}
                    onRunPlaybook={props.onRunPlaybook}
                  />
                )}
                {activeInsightTab === 'persona' && (
                  <PersonaPanel
                    workspaceId={props.workspaceId}
                    apiUrl={apiUrl}
                    seed={props.seed || undefined}
                    handle={(!props.seed && selectedHandle) ? selectedHandle : undefined}
                    onRunPlaybook={props.onRunPlaybook}
                  />
                )}
                {activeInsightTab === 'posts' && (
                  <div className="p-4">
                    <div className="flex justify-between items-center mb-4">
                      <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Recent Posts
                      </h3>
                      {detailHandle && props.onRunPlaybook && (
                        <div className="flex items-center gap-2 bg-gray-50 dark:bg-gray-800/50 p-1.5 rounded-lg border border-gray-200 dark:border-gray-700">
                          <span className="text-xs font-medium text-gray-600 dark:text-gray-300 ml-1">Auto Fetch:</span>
                          <select
                                className="text-xs border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 py-1.5 pl-2 pr-6 focus:ring-2 focus:ring-blue-500 focus:outline-none"
                                value={batchCount}
                                onChange={(e) => setBatchCount(e.target.value)}
                            >
                                <option value="" disabled>Select amount...</option>
                                <option value="100">100 posts</option>
                                <option value="300">300 posts</option>
                                <option value="500">500 posts</option>
                            </select>
                            <button
                              onClick={() => {
                                if (batchCount) {
                                  void handleBatchPin(Number(batchCount));
                                  setBatchCount('');
                                }
                              }}
                              disabled={!batchCount}
                              className="px-3 py-1.5 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-md transition-colors shadow-sm"
                            >
                              Fetch & Pin
                            </button>
                        </div>
                      )}
                    </div>
                    <div className="mb-4 flex flex-wrap gap-2">
                      <span className="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-2.5 py-1 text-[11px] text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
                        Posts <span className="font-semibold text-gray-900 dark:text-gray-100">{gridPosts.length}</span>
                      </span>
                      <span className="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-gray-50 px-2.5 py-1 text-[11px] text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
                        Refs <span className="font-semibold text-gray-900 dark:text-gray-100">{referenceSummary.totalReferences}</span>
                      </span>
                      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300">
                        Analyzed <span className="font-semibold">{referenceSummary.completedPosts}</span>
                      </span>
                      <span className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-2.5 py-1 text-[11px] text-blue-700 dark:border-blue-800 dark:bg-blue-900/20 dark:text-blue-300">
                        Pending <span className="font-semibold">{referenceSummary.pendingPosts}</span>
                      </span>
                      <span className="inline-flex items-center gap-1 rounded-full border border-rose-200 bg-rose-50 px-2.5 py-1 text-[11px] text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-300">
                        Failed <span className="font-semibold">{referenceSummary.failedPosts}</span>
                      </span>
                      {pinFailedAttemptsTotal > 0 && (
                        <span className="inline-flex items-center gap-1 rounded-full border border-rose-200 bg-rose-50 px-2.5 py-1 text-[11px] text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-300">
                          Pin Failed <span className="font-semibold">{pinFailedAttemptsTotal}</span>
                        </span>
                      )}
                      {referenceSummary.pinnedOnlyPosts > 0 && (
                        <span className="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-white px-2.5 py-1 text-[11px] text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
                          Pinned only <span className="font-semibold text-gray-900 dark:text-gray-100">{referenceSummary.pinnedOnlyPosts}</span>
                        </span>
                      )}
                    </div>
                    {pinFailedAttemptsTotal > 0 && (
                      <div className="mb-4 rounded-2xl border border-rose-200 bg-rose-50/70 p-3 dark:border-rose-900/60 dark:bg-rose-950/10">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div>
                            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-rose-700 dark:text-rose-300">
                              Pin Failed
                            </div>
                            <div className="text-xs text-rose-800/90 dark:text-rose-200/80">
                              These items failed before a reference was created, so they do not appear in References.
                            </div>
                          </div>
                          <button
                            onClick={handleRetryPinFailures}
                            disabled={retryingPinFailures}
                            className="inline-flex items-center rounded-full border border-rose-300 bg-white px-3 py-1.5 text-[11px] font-medium text-rose-700 transition-colors hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-rose-800 dark:bg-gray-900/40 dark:text-rose-300 dark:hover:bg-rose-900/20"
                          >
                            {retryingPinFailures ? 'Retrying…' : `Retry ${Math.min(pinFailedAttemptsTotal, 50)} failed pins`}
                          </button>
                        </div>
                        <div className="mt-3 space-y-2">
                          {pinFailedAttempts.slice(0, 5).map((attempt) => (
                            <div
                              key={attempt.dedupe_key}
                              className="rounded-xl border border-rose-200/80 bg-white/80 px-3 py-2 text-xs dark:border-rose-900/50 dark:bg-gray-900/40"
                            >
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="font-medium text-gray-900 dark:text-gray-100">
                                  {attempt.source_shortcode ? `#${attempt.source_shortcode}` : (attempt.image_url || 'Unknown image')}
                                </div>
                                <div className="text-rose-700 dark:text-rose-300">
                                  {attempt.error_kind}
                                  {attempt.failure_count > 1 ? ` · ${attempt.failure_count}x` : ''}
                                </div>
                              </div>
                              <div className="mt-1 text-gray-600 dark:text-gray-300 break-all">
                                {attempt.error_message}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {(latestBatchAttempt || latestCompletedBatch) && (
                      <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50/70 p-3 dark:border-amber-900/60 dark:bg-amber-950/10">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div>
                            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-700 dark:text-amber-300">
                              Batch Target
                            </div>
                            <div className="text-xs text-amber-800/90 dark:text-amber-200/80">
                              Latest request for this account
                            </div>
                          </div>
                          <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium ${latestBatchStatusMeta.className}`}>
                            {latestBatchStatusMeta.label}
                          </span>
                        </div>
                        <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">
                          <div className="rounded-xl border border-amber-200/80 bg-white/80 px-3 py-2 dark:border-amber-900/50 dark:bg-gray-900/40">
                            <div className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">Requested</div>
                            <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">{latestBatchTarget ?? '—'}</div>
                          </div>
                          <div className="rounded-xl border border-amber-200/80 bg-white/80 px-3 py-2 dark:border-amber-900/50 dark:bg-gray-900/40">
                            <div className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">Current Refs</div>
                            <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">{currentReferenceCount}</div>
                          </div>
                          <div className="rounded-xl border border-amber-200/80 bg-white/80 px-3 py-2 dark:border-amber-900/50 dark:bg-gray-900/40">
                            <div className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">Remaining</div>
                            <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">{remainingBatchTarget ?? '—'}</div>
                          </div>
                          <div className="rounded-xl border border-amber-200/80 bg-white/80 px-3 py-2 dark:border-amber-900/50 dark:bg-gray-900/40">
                            <div className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">Last Added</div>
                            <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">{latestBatchMetrics?.pinned_count ?? '—'}</div>
                          </div>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-amber-900/80 dark:text-amber-200/80">
                          {latestBatchProfileName && <span>Session {latestBatchProfileName}</span>}
                          {latestBatchMetrics?.collected_count !== null && latestBatchMetrics?.collected_count !== undefined && (
                            <span>Collected {latestBatchMetrics.collected_count}</span>
                          )}
                          {latestBatchMetrics?.duplicate_count !== null && latestBatchMetrics?.duplicate_count !== undefined && (
                            <span>Duplicates {latestBatchMetrics.duplicate_count}</span>
                          )}
                          {latestCompletedBatch?.completed_at && (
                            <span>Last completed {new Date(latestCompletedBatch.completed_at).toLocaleString()}</span>
                          )}
                        </div>
                      </div>
                    )}
                    {gridLoading ? (
                      <div className="flex items-center justify-center h-32">
                        <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
                      </div>
                    ) : gridPosts.length === 0 ? (
                      <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-8">
                        No posts found. Run content analysis first.
                      </p>
                    ) : (
                      <div className="grid grid-cols-3 gap-2">
                        {gridPosts.map((post, idx) => {
                          const normalizedShortcode = normalizeReferenceShortcode(post.post_shortcode);
                          const postReferenceState = normalizedShortcode
                            ? referenceSummary.byShortcode[normalizedShortcode]
                            : undefined;
                          const isPinned = !!normalizedShortcode && pinnedPostIds.has(normalizedShortcode);
                          const isPinning = post.post_shortcode === pinningPostId;
                          const referenceBadge = postReferenceState
                            ? getReferenceStatusBadge(postReferenceState.status)
                            : null;
                          const referenceThumbnailSrc = postReferenceState?.primaryReferenceId
                            ? getReferenceImageUrl(apiUrl, props.workspaceId, postReferenceState.primaryReferenceId)
                            : undefined;
                          const proxyThumbnailSrc = post.thumbnail_url
                            ? getPostThumbnailUrl(apiUrl, post.post_shortcode || '')
                            : undefined;
                          const thumbnailKey = `${post.id || idx}:${postReferenceState?.primaryReferenceId || ''}:${post.thumbnail_url || ''}`;
                          const thumbnailFailed = !!failedGridThumbnails[thumbnailKey];
                          const thumbnailSrc = thumbnailFailed
                            ? proxyThumbnailSrc
                            : (referenceThumbnailSrc || proxyThumbnailSrc);

                          return (
                            <a
                              key={post.id || idx}
                              href={post.post_url || `https://instagram.com/p/${post.post_shortcode}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="group relative aspect-square bg-gray-100 dark:bg-gray-700 rounded-lg overflow-hidden"
                            >
                              {thumbnailSrc ? (
                                <img
                                  src={thumbnailSrc}
                                  alt={`Post ${post.post_shortcode}`}
                                  className="w-full h-full object-cover"
                                  loading="lazy"
                                  onError={() => {
                                    setFailedGridThumbnails((prev) => {
                                      if (prev[thumbnailKey]) return prev;
                                      return { ...prev, [thumbnailKey]: true };
                                    });
                                  }}
                                />
                              ) : null}
                              <div className={`post-placeholder w-full h-full flex items-center justify-center text-gray-400 ${thumbnailSrc ? 'hidden absolute inset-0' : ''}`}>
                                <Grid3X3 className="w-6 h-6" />
                              </div>
                              {postReferenceState && referenceBadge && (
                                <div className="absolute left-1 top-1 z-10 flex flex-col gap-1 pointer-events-none">
                                  <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold shadow-sm ${referenceBadge.className}`}>
                                    {referenceBadge.label}
                                  </span>
                                  <span className="rounded-full bg-black/60 px-1.5 py-0.5 text-[10px] font-medium text-white shadow-sm">
                                    {postReferenceState.totalReferences} ref{postReferenceState.totalReferences === 1 ? '' : 's'}
                                  </span>
                                </div>
                              )}
                              <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center gap-2 text-white text-xs font-medium">
                                <div className="flex gap-4">
                                  {post.like_count != null && (
                                    <span className="flex items-center gap-1">
                                      <Heart className="w-3.5 h-3.5" />
                                      {formatCount(post.like_count)}
                                    </span>
                                  )}
                                  {post.comment_count != null && (
                                    <span className="flex items-center gap-1">
                                      <MessageCircle className="w-3.5 h-3.5" />
                                      {formatCount(post.comment_count)}
                                    </span>
                                  )}
                                </div>
                                <button
                                  onClick={(e) => {
                                    e.preventDefault();
                                    togglePin(post);
                                  }}
                                  disabled={isPinning}
                                  className={`mt-2 p-2 rounded-full transition-colors ${
                                    isPinned 
                                     ? 'bg-rose-500 text-white hover:bg-rose-600' 
                                     : 'bg-white/20 text-white hover:bg-white/40'
                                  }`}
                                  title={isPinned ? 'Unpin from references' : 'Pin to references'}
                                >
                                  {isPinning ? (
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                  ) : (
                                    <Heart className={`w-4 h-4 ${isPinned ? 'fill-current' : ''}`} />
                                  )}
                                </button>
                              </div>
                              {post.caption_topic && (
                                <span className="absolute bottom-1 left-1 px-1.5 py-0.5 text-[10px] bg-black/50 text-white rounded pointer-events-none">
                                  {post.caption_topic}
                                </span>
                              )}
                            </a>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* ── Account detail cards (when no insight tab selected) ── */}
            {!activeInsightTab && (
              <>
                <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      Account Information
                    </h3>
                    <div className="flex items-center gap-1.5">
                      {/* IG icon — always shown */}
                      <a
                        href={`https://www.instagram.com/${(selectedAccount as DiscoveredAccount).handle}/`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="p-1.5 rounded-md bg-gray-100 dark:bg-gray-700 hover:bg-pink-100 dark:hover:bg-pink-900/30 transition-colors"
                        title="Instagram"
                      >
                        <Instagram className="w-4 h-4 text-pink-600 dark:text-pink-400" />
                      </a>
                      {/* Threads icon — if external_url contains threads.com */}
                      {(() => {
                        const extUrl = latestProfile?.external_url || (selectedAccount as DiscoveredAccount).external_url;
                        if (extUrl && /threads\.(com|net)/i.test(extUrl)) {
                          return (
                            <a
                              href={extUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="p-1.5 rounded-md bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                              title="Threads"
                            >
                              <svg className="w-4 h-4 text-gray-900 dark:text-gray-100" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M12.186 24h-.007c-3.581-.024-6.334-1.205-8.184-3.509C2.35 18.44 1.5 15.586 1.472 12.01v-.017c.03-3.579.879-6.43 2.525-8.482C5.845 1.205 8.6.024 12.18 0h.014c2.746.02 5.043.725 6.826 2.098 1.677 1.29 2.858 3.13 3.509 5.467l-2.04.569c-1.104-3.96-3.898-5.984-8.304-6.015-2.91.022-5.11.936-6.54 2.717C4.307 6.504 3.616 8.914 3.59 12c.025 3.086.718 5.496 2.057 7.164 1.432 1.783 3.631 2.698 6.54 2.717 2.623-.02 4.358-.631 5.8-2.045 1.647-1.613 1.618-3.593 1.09-4.798-.31-.71-.873-1.3-1.634-1.75-.192 1.352-.622 2.446-1.284 3.272-.886 1.102-2.14 1.704-3.73 1.79-1.202.065-2.361-.218-3.259-.801-1.063-.689-1.685-1.74-1.752-2.96-.065-1.17.408-2.265 1.33-3.084.852-.756 2.027-1.2 3.395-1.284.957-.057 1.86.026 2.702.243-.072-.49-.191-.956-.36-1.348-.42-.977-1.17-1.494-2.226-1.536-1.045.023-1.86.344-2.174.856l-1.817-.968c.615-1.157 2.008-1.86 3.933-1.888h.048c1.59.018 2.84.603 3.622 1.69.617.861.952 1.96 1.01 3.263l.013.397c1.244.654 2.174 1.593 2.688 2.768.736 1.685.793 4.477-1.353 6.578C18.39 23.207 16.12 23.968 12.186 24zm-1.248-8.39c-.018 0-.036 0-.055.002-1.095.063-1.831.582-1.806 1.272.023.626.637 1.37 2.222 1.284 1.085-.059 2.591-.57 2.791-3.602a7.073 7.073 0 0 0-3.152 1.044z" />
                              </svg>
                            </a>
                          );
                        }
                        return null;
                      })()}
                      {/* YouTube icon — if external_url or bio contains youtube.com/youtu.be */}
                      {(() => {
                        const extUrl = latestProfile?.external_url || (selectedAccount as DiscoveredAccount).external_url;
                        const bio = latestProfile?.bio || (selectedAccount as DiscoveredAccount).bio || '';
                        const ytPattern = /(?:youtube\.com|youtu\.be)\/([^\s?#]+)/i;
                        const ytMatch = extUrl?.match(ytPattern) || bio.match(ytPattern);
                        const ytUrl = extUrl && ytPattern.test(extUrl) ? extUrl : (ytMatch ? `https://www.youtube.com/${ytMatch[1]}` : null);
                        if (ytUrl) {
                          return (
                            <a
                              href={ytUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="p-1.5 rounded-md bg-gray-100 dark:bg-gray-700 hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
                              title="YouTube"
                            >
                              <Youtube className="w-4 h-4 text-red-600 dark:text-red-400" />
                            </a>
                          );
                        }
                        return null;
                      })()}
                      {/* Facebook icon — if external_url or bio contains facebook.com/fb.com/fb.me */}
                      {(() => {
                        const extUrl = latestProfile?.external_url || (selectedAccount as DiscoveredAccount).external_url;
                        const bio = latestProfile?.bio || (selectedAccount as DiscoveredAccount).bio || '';
                        const fbPattern = /(?:facebook\.com|fb\.com|fb\.me)\/[^\s)]+/i;
                        const fbMatch = extUrl?.match(fbPattern) || bio.match(fbPattern);
                        const fbUrl = extUrl && fbPattern.test(extUrl)
                          ? extUrl
                          : (fbMatch ? `https://${fbMatch[0]}` : null);
                        if (fbUrl) {
                          return (
                            <a
                              href={fbUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="p-1.5 rounded-md bg-gray-100 dark:bg-gray-700 hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors"
                              title="Facebook"
                            >
                              <svg className="w-4 h-4 text-blue-600 dark:text-blue-400" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" />
                              </svg>
                            </a>
                          );
                        }
                        return null;
                      })()}
                      {/* Generic external link — if external_url exists and is NOT a recognized platform */}
                      {(() => {
                        const extUrl = latestProfile?.external_url || (selectedAccount as DiscoveredAccount).external_url;
                        if (extUrl && !/threads\.(com|net)/i.test(extUrl) && !/youtube\.com|youtu\.be/i.test(extUrl) && !/instagram\.com/i.test(extUrl) && !/facebook\.com|fb\.com|fb\.me/i.test(extUrl)) {
                          return (
                            <a
                              href={extUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="p-1.5 rounded-md bg-gray-100 dark:bg-gray-700 hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors"
                              title={extUrl}
                            >
                              <ExternalLink className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                            </a>
                          );
                        }
                        return null;
                      })()}
                    </div>
                  </div>
                  <div className="space-y-2">
                    {(latestProfile?.bio || (selectedAccount as DiscoveredAccount).bio) && (
                      <p className="text-sm text-gray-700 dark:text-gray-300">
                        {latestProfile?.bio || (selectedAccount as DiscoveredAccount).bio}
                      </p>
                    )}
                    <div className="grid grid-cols-3 gap-2">
                      {(latestProfile?.follower_count ?? (selectedAccount as DiscoveredAccount).follower_count) !== undefined && (
                        <div className="text-center">
                          <div className="text-lg font-bold text-gray-900 dark:text-gray-100">
                            {formatCount(((latestProfile?.follower_count ?? (selectedAccount as DiscoveredAccount).follower_count) as number))}
                          </div>
                          <div className="text-xs text-gray-500 dark:text-gray-400">Followers</div>
                        </div>
                      )}
                      {(latestProfile?.following_count ?? (selectedAccount as DiscoveredAccount).following_count) !== undefined && (
                        <div className="text-center">
                          <div className="text-lg font-bold text-gray-900 dark:text-gray-100">
                            {formatCount(((latestProfile?.following_count ?? (selectedAccount as DiscoveredAccount).following_count) as number))}
                          </div>
                          <div className="text-xs text-gray-500 dark:text-gray-400">Following</div>
                        </div>
                      )}
                      {(latestProfile?.post_count ?? (selectedAccount as DiscoveredAccount).post_count) !== undefined && (
                        <div className="text-center">
                          <div className="text-lg font-bold text-gray-900 dark:text-gray-100">
                            {formatCount(((latestProfile?.post_count ?? (selectedAccount as DiscoveredAccount).post_count) as number))}
                          </div>
                          <div className="text-xs text-gray-500 dark:text-gray-400">Posts</div>
                        </div>
                      )}
                    </div>
                    {(latestProfile?.public_email || (selectedAccount as DiscoveredAccount).public_email) && (
                      <a
                        href={`mailto:${latestProfile?.public_email || (selectedAccount as DiscoveredAccount).public_email}`}
                        className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
                      >
                        <Mail className="w-3 h-3" />
                        {latestProfile?.public_email || (selectedAccount as DiscoveredAccount).public_email}
                      </a>
                    )}
                    {(latestProfile?.public_phone_number || (selectedAccount as DiscoveredAccount).public_phone_number) && (
                      <a
                        href={`tel:${latestProfile?.public_phone_number || (selectedAccount as DiscoveredAccount).public_phone_number}`}
                        className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
                      >
                        <Phone className="w-3 h-3" />
                        {latestProfile?.public_phone_number || (selectedAccount as DiscoveredAccount).public_phone_number}
                      </a>
                    )}
                    {(latestProfile?.business_address_json || (selectedAccount as DiscoveredAccount).business_address_json) && (
                      <div className="text-xs text-gray-600 dark:text-gray-400 flex items-center gap-1">
                        <MapPin className="w-3 h-3" />
                        {latestProfile?.business_address_json || (selectedAccount as DiscoveredAccount).business_address_json}
                      </div>
                    )}
                  </div>
                </div>

                <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      Snapshots
                    </h3>
                    <button
                      onClick={() => selectedHandle && onCaptureSnapshot(selectedHandle)}
                      disabled={!selectedHandle || snapshotsLoading}
                      className="px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                    >
                      Capture snapshot
                    </button>
                  </div>
                  {snapshotError && (
                    <div className="text-xs text-red-600 dark:text-red-400 mb-2">
                      {snapshotError}
                    </div>
                  )}
                  {snapshotsLoading ? (
                    <div className="text-sm text-gray-500 dark:text-gray-400">Loading...</div>
                  ) : snapshots.length === 0 ? (
                    <div className="text-sm text-gray-500 dark:text-gray-400">
                      No snapshots yet.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {snapshots.slice(0, 8).map((s: any) => {
                        const meta = s.metadata || {};
                        const c = s.content?.content || s.content || {};
                        const p = c.profile || {};
                        const id = s.id || s.artifact_id;
                        const checked = snapshotCompareIds.includes(id);
                        return (
                          <label key={id} className="flex items-center justify-between gap-3 text-xs">
                            <div className="flex items-center gap-2 min-w-0">
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={(e) => {
                                  const next = e.target.checked
                                    ? [...snapshotCompareIds, id].slice(0, 2)
                                    : snapshotCompareIds.filter((x) => x !== id);
                                  onSnapshotCompareIdsChange(next);
                                }}
                              />
                              <span className="text-gray-500 dark:text-gray-400 truncate">
                                {meta.source_account_handle ? `@${meta.source_account_handle}` : 'Unknown'}
                              </span>
                            </div>
                            <div className="text-gray-900 dark:text-gray-100 whitespace-nowrap">
                              {meta.captured_at ? new Date(meta.captured_at).toLocaleString() : ''}
                            </div>
                            <div className="text-gray-500 dark:text-gray-400 whitespace-nowrap">
                              {p.follower_count ? formatCount(p.follower_count) : (p.follower_count_text || '—')}
                            </div>
                          </label>
                        );
                      })}
                      {snapshotCompareIds.length === 2 && (() => {
                        const a = snapshots.find((x: any) => (x.id || x.artifact_id) === snapshotCompareIds[0]);
                        const b = snapshots.find((x: any) => (x.id || x.artifact_id) === snapshotCompareIds[1]);
                        const pa = (a?.content?.content || a?.content || {})?.profile || {};
                        const pb = (b?.content?.content || b?.content || {})?.profile || {};
                        const delta = (k: string) => {
                          const va = typeof pa[k] === 'number' ? pa[k] : null;
                          const vb = typeof pb[k] === 'number' ? pb[k] : null;
                          if (va === null || vb === null) return null;
                          return va - vb;
                        };
                        const df = delta('follower_count');
                        const dg = delta('following_count');
                        const dp = delta('post_count');
                        return (
                          <div className="mt-2 text-xs text-gray-600 dark:text-gray-300">
                            Compare: Followers {df === null ? '—' : formatCount(df)} / Following {dg === null ? '—' : formatCount(dg)} / Posts {dp === null ? '—' : formatCount(dp)}
                          </div>
                        );
                      })()}
                    </div>
                  )}
                </div>

                <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
                    Metadata
                  </h3>
                  <div className="space-y-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="text-gray-500 dark:text-gray-400">Source</span>
                      <span className="text-gray-900 dark:text-gray-100">
                        {(selectedAccount as DiscoveredAccount).source === 'manual' ? 'Manual Import' :
                          (selectedAccount as DiscoveredAccount).source === 'following_list' ? 'Following List' :
                            (selectedAccount as DiscoveredAccount).source === 'search' ? 'Search' :
                              'Browser Session'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-gray-500 dark:text-gray-400">Fetched At</span>
                      <span className="text-gray-900 dark:text-gray-100">
                        {new Date((selectedAccount as DiscoveredAccount).fetched_at).toLocaleString()}
                      </span>
                    </div>
                    {(selectedAccount as DiscoveredAccount).category && (
                      <div className="flex items-center justify-between">
                        <span className="text-gray-500 dark:text-gray-400">Category</span>
                        <span className="text-gray-900 dark:text-gray-100">
                          {(selectedAccount as DiscoveredAccount).category}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                {(selectedAccount as DiscoveredAccount).sources && (selectedAccount as DiscoveredAccount).sources!.length > 0 && (
                  <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">
                      Sources
                    </h3>
                    <div className="space-y-2 text-xs">
                      {(selectedAccount as DiscoveredAccount).sources!.slice(0, 5).map((s, idx) => (
                        <div key={idx} className="flex items-center justify-between gap-3">
                          <span className="text-gray-500 dark:text-gray-400 truncate">
                            {s.source_account_handle ? `@${s.source_account_handle}` : 'Unknown'}
                          </span>
                          <span className="text-gray-900 dark:text-gray-100">
                            {s.captured_at ? new Date(s.captured_at).toLocaleString() : ''}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">
                    Tags
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {getTagsForHandle(
                      (selectedAccount as DiscoveredAccount).handle,
                      (selectedAccount as DiscoveredAccount).tags
                    ).map((tag) => (
                      <button
                        key={tag}
                        onClick={() => {
                          const handle = (selectedAccount as DiscoveredAccount).handle;
                          const current = getTagsForHandle(handle, (selectedAccount as DiscoveredAccount).tags);
                          setTagsForHandle(handle, current.filter((t) => t !== tag));
                        }}
                        className="px-2 py-1 text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:opacity-80"
                        title="Remove tag"
                      >
                        {tag}
                      </button>
                    ))}
                    {getTagsForHandle(
                      (selectedAccount as DiscoveredAccount).handle,
                      (selectedAccount as DiscoveredAccount).tags
                    ).length === 0 && (
                        <div className="text-xs text-gray-500 dark:text-gray-400">No tags</div>
                      )}
                  </div>

                  <div className="mt-3 flex items-center gap-2">
                    <input
                      type="text"
                      placeholder="Add tag"
                      value={newTagInput}
                      onChange={(e) => onNewTagInputChange(e.target.value)}
                      className="flex-1 px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                      onKeyDown={(e) => {
                        if (e.key !== 'Enter') return;
                        const nextTag = newTagInput.trim();
                        if (!nextTag) return;
                        const handle = (selectedAccount as DiscoveredAccount).handle;
                        const current = getTagsForHandle(handle, (selectedAccount as DiscoveredAccount).tags);
                        setTagsForHandle(handle, [...current, nextTag]);
                        onNewTagInputChange('');
                      }}
                    />
                    <button
                      onClick={() => {
                        const nextTag = newTagInput.trim();
                        if (!nextTag) return;
                        const handle = (selectedAccount as DiscoveredAccount).handle;
                        const current = getTagsForHandle(handle, (selectedAccount as DiscoveredAccount).tags);
                        setTagsForHandle(handle, [...current, nextTag]);
                        onNewTagInputChange('');
                      }}
                      className="px-3 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
                    >
                      Add
                    </button>
                  </div>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div >
  );
}
