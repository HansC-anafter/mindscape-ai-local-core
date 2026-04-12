'use client';

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { MindscapeAPIClient } from '@/api/client';
import type { BrowserProfileController, ConnectedAccount, DiscoveredAccount } from './accounts/types';
import { useLocalAccountTags } from './accounts/hooks/useLocalAccountTags';
import { useConnectedAccounts } from './accounts/hooks/useConnectedAccounts';
import { useDiscoveredAccounts } from './accounts/hooks/useDiscoveredAccounts';
import { applyExecutionBackendHint, executePlaybookStart, fetchTargets } from './accounts/api';
import { useAccountSnapshots } from './accounts/hooks/useAccountSnapshots';
import { useAccountsAnalytics } from './accounts/hooks/useAccountsAnalytics';
import { useAccountsRunStatus } from './accounts/hooks/useAccountsRunStatus';
import { useImportHandles } from './accounts/hooks/useImportHandles';
import { useSeedOptions } from './accounts/hooks/useSeedOptions';
import { useAvatarRefresh } from './accounts/hooks/useAvatarRefresh';
import type { SeedInfo } from './accounts/insightsApi';
import { buildSourceOptions, filterConnectedAccounts, filterDiscoveredAccounts, filterTargets } from './accounts/selectors';
import { TargetsFilters } from './accounts/components/TargetsFilters';
import { AccountsAnalyticsPanel } from './accounts/components/AccountsAnalyticsPanel';
import { AccountDetailPanel } from './accounts/components/AccountDetailPanel';
import { AccountsTabs } from './accounts/components/AccountsTabs';
import { AccountsHeaderActions } from './accounts/components/AccountsHeaderActions';
import { AccountsOverlays } from './accounts/components/AccountsOverlays';
import { SourcesTab } from './accounts/components/SourcesTab';
import { CapturesTab } from './accounts/components/CapturesTab';
import { TargetsTab } from './accounts/components/TargetsTab';
import { InsightsTab } from './accounts/components/InsightsTab';
import { useIGWorkspaceEvents } from '../hooks/useIGWorkspaceEvents';
import { useExecutionPolling } from '@/hooks/useExecutionPolling';
import { useExecutionActions } from '../workbench/components/WorkbenchExecutionPanel/hooks/useExecutionActions';
import { injectWorkspaceIGBrowserProfileInputs } from '../browserProfile';

interface AccountsPanelProps {
  workspaceId: string;
  apiUrl: string;
  browserProfile: BrowserProfileController;
  onAccountSelect?: (accountId: string) => void;
  recentRuns?: any[];
}

export default function AccountsPanel({
  workspaceId,
  apiUrl,
  browserProfile,
  onAccountSelect,
  recentRuns = []
}: AccountsPanelProps) {
  const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);
  const [activeTab, setActiveTab] = useState<'sources' | 'targets' | 'captures' | 'analytics' | 'insights'>('targets');
  const [insightsSeed, setInsightsSeed] = useState<string>('');
  const [targetsViewMode, setTargetsViewMode] = useState<'grid' | 'list'>('grid');
  const [sourceFilterKey, setSourceFilterKey] = useState<string>('all');
  const [seedFilterKey, setSeedFilterKey] = useState<string>('all');
  const [selectedAccount, setSelectedAccount] = useState<ConnectedAccount | DiscoveredAccount | null>(null);
  const [selectedSeed, setSelectedSeed] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [importHandles, setImportHandles] = useState('');
  const [showFollowingAnalyzer, setShowFollowingAnalyzer] = useState(false);
  const [captureSnapshotFocusToken, setCaptureSnapshotFocusToken] = useState(0);
  const [recrawlSeed, setRecrawlSeed] = useState<string | undefined>(undefined);
  const [newTagInput, setNewTagInput] = useState<string>('');
  const [analyticsMetric, setAnalyticsMetric] = useState<'followers' | 'following' | 'posts'>('followers');
  const [analyticsBucket, setAnalyticsBucket] = useState<string | null>(null);
  const [tagFilter, setTagFilter] = useState<string>('all');
  const [activeIGExecutionId, setActiveIGExecutionId] = useState<string | null>(null);
  const lastExecutionEventAtRef = useRef<number>(0);
  const lastVisitedAccountRef = useRef<string | null>(null);


  const { localTags, setTagsForHandle, getTagsForHandle } = useLocalAccountTags(workspaceId);
  const { browserSession } = browserProfile;
  const { connectedAccounts } = useConnectedAccounts({ apiUrl, workspaceId });
  // Extract raw seed value from seedFilterKey (e.g. "seed:dearruigallery" → "dearruigallery")
  const activeSeed = seedFilterKey !== 'all' && seedFilterKey.startsWith('seed:')
    ? seedFilterKey.slice('seed:'.length)
    : undefined;
  const needsAccountDetailData =
    !!selectedAccount && !('channel_config_id' in selectedAccount);
  const needsDiscoveredAccounts =
    activeTab === 'targets' || activeTab === 'analytics' || activeTab === 'captures' || needsAccountDetailData;
  const needsSeedOptions =
    activeTab === 'targets' || activeTab === 'analytics' || needsAccountDetailData;
  const {
    allAccounts,
    total: totalAccountsCount,
    hasMore: hasMoreAccounts,
    loadMore: loadMoreAccounts,
    refreshTotal: refreshAccountsTotal,
    refreshData: refreshAccountsData,
    refreshSingleAccount,
    reset: resetAccounts,
    loading: discoveredAccountsLoading,
    loadingMore: discoveredAccountsLoadingMore,
    error: discoveredAccountsError,
  } = useDiscoveredAccounts({
    apiUrl,
    workspaceId,
    seed: activeSeed,
    search: searchQuery,
    enabled: needsDiscoveredAccounts,
  });
  const { seedOptions, refresh: refreshSeedOptions } = useSeedOptions({
    apiUrl,
    workspaceId,
    enabled: needsSeedOptions && (!needsDiscoveredAccounts || !discoveredAccountsLoading),
    initialDelayMs: activeTab === 'targets' ? 750 : 0,
  });
  const accountDetailSeeds = useMemo<SeedInfo[]>(() => (
    seedOptions.map((option) => ({
      seed: option.label,
      target_count: option.count,
      visited_count: 0,
      expected_count: null,
      bio: null,
      profile_picture_url: null,
      last_crawled: null,
      has_tags: false,
      has_posts: false,
      has_network: false,
      has_personas: false,
    }))
  ), [seedOptions]);

  // Auto-switch to targets tab and scroll to account when event fires
  const activeTabRef = useRef(activeTab);
  activeTabRef.current = activeTab;
  const allAccountsRef = useRef(allAccounts);
  allAccountsRef.current = allAccounts;
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      const handle = typeof detail === 'string' ? detail : detail?.handle;
      const seed = typeof detail === 'string' ? null : detail?.seed;
      if (!handle) return;

      if (seed) {
        setSeedFilterKey(`seed:${seed}`);
      }
      setSourceFilterKey('all');

      if (activeTabRef.current !== 'targets') {
        setActiveTab('targets');
        setSearchQuery('');
        setTimeout(() => {
          window.dispatchEvent(new CustomEvent('ig:scroll-to-account', { detail: { handle, seed } }));
        }, 300);
        e.stopImmediatePropagation();
        return;
      }
      const cleanHandle = handle.replace(/^@/, '');
      const normalizedHandle = cleanHandle.toLowerCase();
      const idxInAll = allAccountsRef.current.findIndex(
        (t: any) => ((t?.handle || '').toString().toLowerCase() === normalizedHandle)
      );
      if (idxInAll < 0) {
        setSearchQuery(cleanHandle);
        setTimeout(() => {
          window.dispatchEvent(new CustomEvent('ig:scroll-to-account', { detail: { handle, seed } }));
        }, 600);
        e.stopImmediatePropagation();
      }
    };
    window.addEventListener('ig:scroll-to-account', handler as EventListener);
    return () => window.removeEventListener('ig:scroll-to-account', handler as EventListener);
  }, []);
  const {
    refresh: refreshAvatars,
    loading: avatarRefreshLoading,
    result: avatarRefreshResult,
    error: avatarRefreshError,
  } = useAvatarRefresh({ apiUrl });

  // Sync running execution ID from polling status to enable SSE/refresh
  const { runStatus } = useAccountsRunStatus({ apiUrl, workspaceId });

  // Execution actions for SourcesTab seed cards (rerun / cancel)
  const {
    rerunBusyId: seedRerunBusyId,
    rerunExecution: seedRerunExecution,
    cancelBusyId: seedCancelBusyId,
    cancelExecution: seedCancelExecution,
  } = useExecutionActions({ apiUrl, workspaceId });
  // Bootstrap the active execution if the page loaded mid-run.
  // Ongoing lifecycle alignment comes from the canonical workspace bus.
  useEffect(() => {
    if (
      runStatus?.execution_id &&
      (runStatus?.playbook_code === 'ig_analyze_following' ||
        runStatus?.playbook_code === 'ig_capture_account_snapshot')
    ) {
      setActiveIGExecutionId((prev) => (prev === runStatus.execution_id ? prev : runStatus.execution_id));
    }
  }, [runStatus?.execution_id, runStatus?.playbook_code]);

  useEffect(() => {
    lastVisitedAccountRef.current = null;
  }, [activeIGExecutionId]);

  // Filter change resets are handled inside useDiscoveredAccounts automatically.

  useIGWorkspaceEvents({
    workspaceId,
    apiUrl,
    onEvent: (_event, metadata) => {
      const playbookCode = (metadata.playbookCode || '').toString();
      if (
        playbookCode !== 'ig_analyze_following' &&
        playbookCode !== 'ig_capture_account_snapshot'
      ) {
        return;
      }

      const executionId = (metadata.executionId || '').toString().trim();
      if (!executionId) return;

      const lifecycleState = (metadata.lifecycleState || '').toString().toUpperCase();
      if (lifecycleState === 'READY' || lifecycleState === 'RUNNING') {
        setActiveIGExecutionId((prev) => (prev === executionId ? prev : executionId));
      }
    },
  });

  useEffect(() => {
    const handler = () => {
      setRecrawlSeed(undefined);
      setActiveTab('captures');
      setShowFollowingAnalyzer(true);
    };
    if (typeof window !== 'undefined') {
      window.addEventListener('ig:open-following-analyzer', handler as EventListener);
    }
    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener('ig:open-following-analyzer', handler as EventListener);
      }
    };
  }, []);

  // SSE-driven data refresh: re-fetch loaded pages in-place (merge mode)
  // so per-visit page stats appear on cards without scroll snap-back.
  //
  // Seed dropdown refresh is tab-independent — counts must stay current
  // even when the user is on a different tab.
  const pollFnCombined = useCallback(() => {
    void refreshAccountsTotal();
    void refreshAccountsData();
    void refreshSeedOptions();
  }, [refreshAccountsTotal, refreshAccountsData, refreshSeedOptions]);

  const dispatchExecutionStarted = useCallback((
    playbookCode: string,
    executionId?: string | null,
    inputs?: Record<string, unknown>,
  ) => {
    const execId = (executionId || '').toString().trim();
    if (!execId || typeof window === 'undefined') return;
    window.dispatchEvent(
      new CustomEvent('mindscape:execution_started', {
        detail: {
          workspaceId,
          executionId: execId,
          playbookCode,
          inputs: inputs || {},
          startedAt: new Date().toISOString(),
        },
      })
    );
  }, [workspaceId]);

  const startActiveProfilePlaybook = useCallback(async (
    playbookCode: string,
    params: Record<string, unknown>
  ) => {
    const queryParams = new URLSearchParams({
      playbook_code: playbookCode,
      workspace_id: workspaceId,
      profile_id: 'default-user',
    });
    applyExecutionBackendHint(queryParams, workspaceId);
    const resp = await executePlaybookStart(client, queryParams, {
      inputs: injectWorkspaceIGBrowserProfileInputs(workspaceId, {
        ...params,
        workspace_id: workspaceId,
        user_data_dir: browserSession.profilePath,
      }),
    });
    if (resp.ok) {
      const data = await resp.json().catch(() => ({}));
      const execId = data.execution_id || data.result?.execution_id;
      dispatchExecutionStarted(playbookCode, execId, params);
    }
    return resp;
  }, [browserSession.profilePath, client, dispatchExecutionStarted, workspaceId]);

  useExecutionPolling({
    executionId: activeIGExecutionId ?? null,
    workspaceId,
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
        setActiveIGExecutionId(null);
        void resetAccounts();
        void refreshSeedOptions();
        return;
      }

      const progress = event?.data?.progress ?? event?.progress;
      const stage = progress?.stage;

      // Skip events without a recognized stage — these come from
      // executions that have not written their progress artifact yet.
      if (!stage) return;

      lastExecutionEventAtRef.current = Date.now();

      // Seed dropdown refresh fires regardless of active tab
      if (stage === 'scrolling' || stage === 'search_extract' || stage === 'initial_collect') {
        void refreshSeedOptions();
      }

      // Targets-specific refreshes only when viewing the targets tab
      if (activeTab !== 'targets') return;

      if (stage === 'scrolling' || stage === 'search_extract' || stage === 'initial_collect') {
        void refreshAccountsTotal();
      } else if (stage === 'visiting_pages') {
        // Visiting pages enriches one card — targeted single-card fetch.
        // SSE heartbeat fires every ~3s; if multiple accounts were visited
        // between heartbeats, the previous one would be skipped.  Always
        // refresh the PREVIOUS account (catch-up) alongside the current one.
        const currentAccountRaw = progress?.current_account;
        const currentAccount = typeof currentAccountRaw === 'string'
          ? currentAccountRaw.replace(/^@/, '').trim()
          : '';
        if (currentAccount) {
          const prevRaw = lastVisitedAccountRef.current;
          const prev = typeof prevRaw === 'string'
            ? prevRaw.replace(/^@/, '').trim()
            : '';
          if (prev && prev.toLowerCase() !== currentAccount.toLowerCase()) {
            void refreshSingleAccount(prev);
          }
          lastVisitedAccountRef.current = currentAccount;
          void refreshSingleAccount(currentAccount);
        }
        // Safety net: merge-refresh loaded page(s) in case current_account
        // isn't resolvable in the current filtered list.
        void refreshAccountsData();
      }
    },
    pollIntervalMs: 10_000,
    // Discovery updates now come from the workspace lifecycle bus plus polling.
    // A dedicated execution SSE here was still competing with the sidebar cards.
    enableSSE: false,
    enablePollingFallback: true,
    sseDebounceMs: 5_000,
    pollFn: activeTab === 'targets' ? pollFnCombined : refreshSeedOptions,
  });

  // If account detail panel is open, keep it in sync when underlying list updates.
  useEffect(() => {
    if (!selectedAccount) return;
    if ('channel_config_id' in selectedAccount) return;
    const handle = (selectedAccount as DiscoveredAccount).handle;
    const next = allAccounts.find((a) => a.handle === handle);
    if (!next) return;
    // Only update if anything meaningful changed.
    const prev = selectedAccount as DiscoveredAccount;
    const changed =
      prev.fetched_at !== next.fetched_at ||
      prev.follower_count !== next.follower_count ||
      prev.following_count !== next.following_count ||
      prev.post_count !== next.post_count ||
      prev.bio !== next.bio ||
      prev.profile_picture_url !== next.profile_picture_url;
    if (!changed) return;
    setSelectedAccount({ ...(next as DiscoveredAccount) });
  }, [allAccounts, selectedAccount]);
  const {
    snapshots,
    snapshotsLoading,
    snapshotError,
    snapshotCompareIds,
    setSnapshotCompareIds,
    snapshotHandleInput,
    setSnapshotHandleInput,
    captureSnapshot,
  } = useAccountSnapshots({
    apiUrl,
    workspaceId,
    selectedAccount,
    browserProfilePath: browserSession.profilePath,
    onAfterCapture: resetAccounts,
    onRefreshSelectedAccount: () => {
      if (selectedAccount && !('channel_config_id' in selectedAccount)) {
        setSelectedAccount({ ...(selectedAccount as DiscoveredAccount) });
      }
    },
  });
  const { importHandles: runImportHandles } = useImportHandles({
    apiUrl,
    workspaceId,
    onStarted: (data) => {
      const handles = importHandles
        .split('\n')
        .map((h) => h.trim())
        .filter((h) => h.length > 0);
      alert(`Started importing ${handles.length} account(s), execution ID: ${data.execution_id}`);
    },
    onError: alert,
    onFinally: () => { },
    onSetLoading: setLoading,
    onCloseDialog: () => setShowImportDialog(false),
    onClearInput: () => setImportHandles(''),
    onScheduleRefresh: (delayMs) => setTimeout(() => resetAccounts(), delayMs),
  });
  const filteredConnectedAccounts = filterConnectedAccounts(connectedAccounts, searchQuery);
  const filteredDiscoveredAccounts = filterDiscoveredAccounts(allAccounts, searchQuery);
  const sourceOptions = buildSourceOptions(allAccounts);
  // Seed filter is now server-side (passed to useDiscoveredAccounts), only source filter remains client-side
  const filteredTargetsAll = filterTargets(filteredDiscoveredAccounts, { sourceFilterKey, seedFilterKey: 'all' });
  const targetsLoading = loading || discoveredAccountsLoading;
  const { loading: analyticsLoading, error: analyticsError, rows: analyticsRows } = useAccountsAnalytics({
    apiUrl,
    workspaceId,
    enabled: activeTab === 'analytics',
  });

  if (selectedAccount) {
    return (
      <AccountDetailPanel
        apiUrl={apiUrl}
        workspaceId={workspaceId}
        selectedAccount={selectedAccount}
        onBack={() => { setSelectedAccount(null); setSelectedSeed(null); }}
        snapshots={snapshots}
        snapshotsLoading={snapshotsLoading}
        snapshotError={snapshotError}
        snapshotCompareIds={snapshotCompareIds}
        onSnapshotCompareIdsChange={setSnapshotCompareIds}
        onCaptureSnapshot={captureSnapshot}
        newTagInput={newTagInput}
        onNewTagInputChange={setNewTagInput}
        setTagsForHandle={setTagsForHandle}
        getTagsForHandle={getTagsForHandle}
        seed={selectedSeed || undefined}
        allSeeds={accountDetailSeeds}
        onRunPlaybook={async (playbookCode, params) => {
          try {
            await startActiveProfilePlaybook(playbookCode, params);
          } catch (e) {
            console.error('[AccountsPanel] onRunPlaybook error:', e);
          }
        }}
        onAddToSeed={async (handle) => {
          try {
            const { createInsightsApi } = await import('./accounts/insightsApi');
            const api = createInsightsApi(apiUrl);

            await api.addSeed(workspaceId, handle);
            void refreshSeedOptions();

            void startActiveProfilePlaybook('ig_analyze_following', {
              target_username: handle,
              run_mode: 'full',
              visit_account_pages: true,
            }).catch((e) => {
              console.error('[AccountsPanel] background ig_analyze_following start error:', e);
            });
          } catch (e) {
            console.error('[AccountsPanel] onAddToSeed error:', e);
            throw e;
          }
        }}
      />
    );
  }

  return (
    <div className="h-full flex flex-col p-3">
      <div className="grid grid-cols-[auto,auto] items-center justify-between gap-2 mb-3 border-b border-gray-200 dark:border-gray-700">
        <AccountsTabs
          activeTab={activeTab}
          onTabChange={setActiveTab}
        />
        <AccountsHeaderActions
          activeTab={activeTab}
          targetsViewMode={targetsViewMode}
          onTargetsViewModeChange={setTargetsViewMode}
          onOpenFollowingAnalyzer={() => setShowFollowingAnalyzer(true)}
          onOpenImportDialog={() => setShowImportDialog(true)}
        />
      </div>

      {activeTab === 'targets' && (
        <TargetsFilters
          searchQuery={searchQuery}
          onSearchQueryChange={setSearchQuery}
          sourceFilterKey={sourceFilterKey}
          onSourceFilterKeyChange={setSourceFilterKey}
          seedFilterKey={seedFilterKey}
          onSeedFilterKeyChange={setSeedFilterKey}
          sourceOptions={sourceOptions}
          seedOptions={seedOptions}
        />
      )}

      {activeTab === 'sources' && (
        <SourcesTab
          workspaceId={workspaceId}
          apiUrl={apiUrl}
          filteredConnectedAccounts={filteredConnectedAccounts}
          onOpenCaptureSnapshot={() => {
            setSnapshotHandleInput('');
            setActiveTab('captures');
            setCaptureSnapshotFocusToken((prev) => prev + 1);
          }}
          onViewInsights={async (seed) => {
            // Set a placeholder immediately, then enrich with API data
            const placeholder: DiscoveredAccount = {
              account_id: `seed_${seed}`,
              handle: seed,
              name: seed,
              fetched_at: new Date().toISOString(),
              source: 'following_list' as const,
            };
            setSelectedAccount(placeholder);
            setSelectedSeed(seed);

            // Fetch the richest profile for this handle across all seeds
            try {
              const resp = await fetchTargets(client, {
                workspace_id: workspaceId,
                handle: seed,
                limit: 10,
              });
              if (resp.ok) {
                const data = await resp.json();
                // Find exact handle matches and pick the row with most data
                const exact = (data.targets || []).filter(
                  (t: any) => t.handle?.toLowerCase() === seed.toLowerCase()
                );
                if (exact.length > 0) {
                  const best = exact.reduce((a: any, b: any) => {
                    const score = (t: any) =>
                      (t.bio ? 1 : 0) + (t.follower_count != null ? 1 : 0) +
                      (t.following_count != null ? 1 : 0) + (t.post_count != null ? 1 : 0) +
                      (t.profile_picture_url ? 1 : 0) + (t.name ? 1 : 0);
                    return score(b) > score(a) ? b : a;
                  });
                  const enriched: DiscoveredAccount = {
                    account_id: `seed_${seed}`,
                    handle: best.handle,
                    name: best.name || seed,
                    bio: best.bio || undefined,
                    profile_picture_url: best.profile_picture_url || undefined,
                    follower_count: best.follower_count ?? undefined,
                    following_count: best.following_count ?? undefined,
                    post_count: best.post_count ?? undefined,
                    external_url: best.external_url || undefined,
                    is_verified: best.is_verified ?? false,
                    fetched_at: best.captured_at || new Date().toISOString(),
                    source: 'following_list' as const,
                  };
                  setSelectedAccount(enriched);
                }
              }
            } catch (e) {
              console.error('Failed to fetch seed profile:', e);
            }
          }}
          onReCrawl={(seed) => {
            setRecrawlSeed(seed);
            setShowFollowingAnalyzer(true);
          }}
          recentRuns={recentRuns}
          onRerun={seedRerunExecution}
          onCancel={seedCancelExecution}
          rerunBusyId={seedRerunBusyId}
          cancelBusyId={seedCancelBusyId}
        />
      )}

      {activeTab === 'captures' && (
        <CapturesTab
          snapshotHandleInput={snapshotHandleInput}
          onSnapshotHandleInputChange={setSnapshotHandleInput}
          onCaptureSnapshot={() => captureSnapshot(snapshotHandleInput)}
          captureDisabled={snapshotsLoading || !snapshotHandleInput.trim()}
          snapshotError={snapshotError}
          snapshotFocusToken={captureSnapshotFocusToken}
          onOpenFollowingAnalyzer={() => setShowFollowingAnalyzer(true)}
          onRefreshTargets={() => {
            void resetAccounts();
            setActiveTab('targets');
          }}
          onRefreshAvatars={() => refreshAvatars(allAccounts.map((a) => a.handle))}
          avatarRefreshLoading={avatarRefreshLoading}
          avatarRefreshResult={avatarRefreshResult}
          avatarRefreshError={avatarRefreshError}
          totalAccounts={allAccounts.length}
        />
      )}

      {activeTab === 'analytics' && (
        <AccountsAnalyticsPanel
          analyticsMetric={analyticsMetric}
          onAnalyticsMetricChange={setAnalyticsMetric}
          sourceFilterKey={sourceFilterKey}
          onSourceFilterKeyChange={setSourceFilterKey}
          sourceOptions={sourceOptions}
          analyticsLoading={analyticsLoading}
          analyticsError={analyticsError}
          analyticsRows={analyticsRows}
          localTags={localTags}
          tagFilter={tagFilter}
          onTagFilterChange={setTagFilter}
          analyticsBucket={analyticsBucket}
          onAnalyticsBucketChange={setAnalyticsBucket}
          discoveredAccounts={allAccounts}
          onSelectAccount={(acc) => {
            setSelectedAccount(acc);
            onAccountSelect?.(acc.account_id);
          }}
        />
      )}

      {activeTab === 'insights' && (
        <InsightsTab
          workspaceId={workspaceId}
          apiUrl={apiUrl}
          initialSeed={insightsSeed || undefined}
          onRunPlaybook={async (playbookCode, params) => {
            try {
              await startActiveProfilePlaybook(playbookCode, params);
            } catch (e) {
              console.error('[AccountsPanel] onRunPlaybook error:', e);
            }
          }}
        />
      )}

      {activeTab === 'targets' && (
        <TargetsTab
          loading={targetsLoading}
          error={discoveredAccountsError}
          filteredTargets={filteredTargetsAll}
          searchQuery={searchQuery}
          targetsViewMode={targetsViewMode}
          apiUrl={apiUrl}
          getTagsForHandle={getTagsForHandle}
          onSelect={(account) => {
            setSelectedAccount(account);
            onAccountSelect?.(account.account_id);
          }}
          onRetry={() => { void resetAccounts(); }}
          loadMore={loadMoreAccounts}
          hasMore={hasMoreAccounts}
          loadingMore={discoveredAccountsLoadingMore}
        />
      )}

      <AccountsOverlays
        showImportDialog={showImportDialog}
        importHandles={importHandles}
        onImportHandlesChange={setImportHandles}
        onConfirmImport={() => runImportHandles(importHandles)}
        confirmImportDisabled={loading || !importHandles.trim()}
        onCancelImport={() => {
          setShowImportDialog(false);
          setImportHandles('');
        }}
        showFollowingAnalyzer={showFollowingAnalyzer}
        onCloseFollowingAnalyzer={() => {
          setShowFollowingAnalyzer(false);
          setRecrawlSeed(undefined);
        }}
        workspaceId={workspaceId}
        apiUrl={apiUrl}
        onFollowingAnalyzerComplete={() => {
          void resetAccounts();
          setActiveTab('targets');
        }}
        defaultUserDataDir={browserSession.profilePath}
        defaultUsername={recrawlSeed}
      />
    </div>
  );
}
