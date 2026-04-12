import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { Plus, Loader2, Search, LayoutList, LayoutGrid } from 'lucide-react';

import type { SeedInfo } from '../insightsApi';
import { createInsightsApi } from '../insightsApi';
import type { ConnectedAccount } from '../types';
import { ConnectedAccountsCard } from './ConnectedAccountsCard';
import { SeedCard } from './SeedCard';
import { useSeedExecutions, type RunInfo } from '../hooks/useSeedExecutions';
import type { IGDebugInfo } from './SeedExecutionBar';
import { hasIGRefreshHint, useIGWorkspaceEvents } from '../../../hooks/useIGWorkspaceEvents';

type SortKey = 'targets' | 'recent' | 'alpha' | 'completion';
type StatusFilter = 'all' | 'running' | 'complete' | 'incomplete';

const seedsCache = new Map<string, SeedInfo[]>();

export function SourcesTab(props: {
  workspaceId: string;
  apiUrl: string;
  filteredConnectedAccounts: ConnectedAccount[];
  onOpenCaptureSnapshot: () => void;
  onViewInsights: (seed: string) => void;
  onReCrawl: (seed: string) => void;
  recentRuns?: RunInfo[];
  onRefreshRuns?: () => void;
  onRerun?: (executionId: string, overrideInputs?: Record<string, any>) => Promise<void>;
  onCancel?: (executionId: string) => Promise<void>;
  rerunBusyId?: string | null;
  cancelBusyId?: string | null;
  igDebug?: IGDebugInfo | null;
  igExecutionId?: string | null;
}) {
  const {
    workspaceId, apiUrl, filteredConnectedAccounts,
    onOpenCaptureSnapshot,
    onViewInsights, onReCrawl, recentRuns = [],
    onRefreshRuns, onRerun, onCancel,
    rerunBusyId, cancelBusyId, igDebug, igExecutionId,
  } = props;

  const cacheKey = `${apiUrl}::${workspaceId}`;
  const [seeds, setSeeds] = useState<SeedInfo[]>(() => seedsCache.get(cacheKey) || []);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('targets');
  const [sortAsc, setSortAsc] = useState(false);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [compactMode, setCompactMode] = useState(false);
  const [expandedSeeds, setExpandedSeeds] = useState<Set<string>>(new Set());
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const seedsCountRef = useRef(seeds.length);

  useEffect(() => {
    seedsCountRef.current = seeds.length;
  }, [seeds.length]);

  const api = useMemo(() => createInsightsApi(apiUrl), [apiUrl]);

  const loadSeeds = useCallback(async (background = false) => {
    const showBlockingLoading = !background && seedsCountRef.current === 0;
    if (showBlockingLoading) {
      setLoading(true);
    }
    try {
      const result = await api.fetchSeeds(workspaceId);
      seedsCache.set(cacheKey, result);
      setSeeds(result);
    } catch (e) {
      console.error('Failed to load seeds', e);
    } finally {
      if (showBlockingLoading) {
        setLoading(false);
      }
    }
  }, [api, cacheKey, workspaceId]);

  useEffect(() => { loadSeeds(); }, [loadSeeds]);

  const scheduleRefresh = useCallback(() => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = setTimeout(() => {
      void loadSeeds(true);
    }, 2000);
  }, [loadSeeds]);

  const patchSeedExecution = useCallback((seedName: string, executionPatch: Partial<NonNullable<SeedInfo['execution']>>) => {
    const normalizedSeed = seedName.toLowerCase();
    setSeeds((prev) =>
      prev.map((seed) => {
        if (seed.seed.toLowerCase() !== normalizedSeed) return seed;
        return {
          ...seed,
          execution: {
            execution_id: seed.execution?.execution_id ?? null,
            status: seed.execution?.status ?? null,
            queue_position: seed.execution?.queue_position ?? null,
            blocked_reason: seed.execution?.blocked_reason ?? null,
            failure_reason: seed.execution?.failure_reason ?? null,
            created_at: seed.execution?.created_at ?? null,
            started_at: seed.execution?.started_at ?? null,
            completed_at: seed.execution?.completed_at ?? null,
            ...executionPatch,
          },
        };
      }),
    );
  }, []);

  const refreshSeedsNow = useCallback(async () => {
    await loadSeeds(true);
    scheduleRefresh();
    onRefreshRuns?.();
  }, [loadSeeds, onRefreshRuns, scheduleRefresh]);

  useEffect(() => () => {
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  useEffect(() => {
    const handleFocusRefresh = () => {
      void loadSeeds(true);
    };
    const handleVisibilityRefresh = () => {
      if (document.visibilityState === 'visible') {
        void loadSeeds(true);
      }
    };
    window.addEventListener('focus', handleFocusRefresh);
    document.addEventListener('visibilitychange', handleVisibilityRefresh);
    return () => {
      window.removeEventListener('focus', handleFocusRefresh);
      document.removeEventListener('visibilitychange', handleVisibilityRefresh);
    };
  }, [loadSeeds]);

  useIGWorkspaceEvents({
    workspaceId,
    apiUrl,
    onEvent: (_event, metadata) => {
      if (metadata.playbookCode !== 'ig_analyze_following') return;
      if (!hasIGRefreshHint(metadata, 'sources')) return;
      scheduleRefresh();
    },
  });

  const handleRemove = async (handle: string) => {
    try {
      await api.removeSeed(workspaceId, handle);
      setSeeds((prev) => prev.filter((s) => s.seed !== handle));
    } catch (e) {
      console.error('Failed to remove seed', e);
    }
  };

  const seedExecutionMap = useSeedExecutions(seeds, recentRuns);

  const handleSeedRerun = useCallback(async (seedName: string, executionId: string, overrideInputs?: Record<string, any>) => {
    if (!onRerun) return;
    patchSeedExecution(seedName, {
      status: 'pending',
      queue_position: null,
      blocked_reason: 'refreshing',
      failure_reason: null,
      started_at: null,
      completed_at: null,
      created_at: new Date().toISOString(),
    });
    try {
      await onRerun(executionId, {
        target_username: seedName,
        ...(overrideInputs || {}),
      });
    } finally {
      void refreshSeedsNow();
    }
  }, [onRerun, patchSeedExecution, refreshSeedsNow]);

  const handleSeedCancel = useCallback(async (seedName: string, executionId: string) => {
    if (!onCancel) return;
    try {
      await onCancel(executionId);
    } finally {
      patchSeedExecution(seedName, {
        blocked_reason: null,
        queue_position: null,
      });
      void refreshSeedsNow();
    }
  }, [onCancel, patchSeedExecution, refreshSeedsNow]);

  const debugSeed = igExecutionId
    ? Array.from(seedExecutionMap.entries()).find(([_, exec]) => {
      const id = (exec.latestRun?.execution_id || exec.latestRun?.id || '').toString();
      return id === igExecutionId;
    })?.[0] || null
    : null;

  const getSeedStatus = useCallback((seedKey: string) => {
    return (seedExecutionMap.get(seedKey)?.status as any) || 'idle';
  }, [seedExecutionMap]);

  // Filter + Sort
  const filteredSeeds = useMemo(() => {
    let result = [...seeds];

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      result = result.filter((s) =>
        s.seed.toLowerCase().includes(q) || (s.bio || '').toLowerCase().includes(q)
      );
    }

    if (statusFilter !== 'all') {
      result = result.filter((s) => {
        const status = getSeedStatus(s.seed.toLowerCase());
        if (statusFilter === 'running') return status === 'running' || status === 'pending';
        if (statusFilter === 'complete') return s.visited_count >= s.target_count && s.target_count > 0;
        return s.target_count === 0 || s.visited_count < s.target_count;
      });
    }

    result.sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case 'targets': cmp = b.target_count - a.target_count; break;
        case 'recent': {
          const ta = a.last_crawled ? new Date(a.last_crawled).getTime() : 0;
          const tb = b.last_crawled ? new Date(b.last_crawled).getTime() : 0;
          cmp = tb - ta; break;
        }
        case 'alpha': cmp = a.seed.localeCompare(b.seed); break;
        case 'completion': {
          const ca = a.target_count > 0 ? a.visited_count / a.target_count : -1;
          const cb = b.target_count > 0 ? b.visited_count / b.target_count : -1;
          cmp = cb - ca; break;
        }
      }
      if (cmp === 0) cmp = a.seed.localeCompare(b.seed);
      return sortAsc ? -cmp : cmp;
    });

    return result;
  }, [seeds, searchQuery, statusFilter, sortKey, sortAsc, getSeedStatus]);

  const statusCounts = useMemo(() => {
    let running = 0, complete = 0, incomplete = 0;
    for (const s of seeds) {
      const status = getSeedStatus(s.seed.toLowerCase());
      if (status === 'running' || status === 'pending') running++;
      if (s.visited_count >= s.target_count && s.target_count > 0) complete++;
      else incomplete++;
    }
    return { all: seeds.length, running, complete, incomplete };
  }, [seeds, getSeedStatus]);

  const statusTabs: { key: StatusFilter; label: string; count: number }[] = [
    { key: 'all', label: 'All', count: statusCounts.all },
    { key: 'running', label: 'Running', count: statusCounts.running },
    { key: 'complete', label: 'Complete', count: statusCounts.complete },
    { key: 'incomplete', label: 'Incomplete', count: statusCounts.incomplete },
  ];

  const sortOptions: { key: SortKey; label: string }[] = [
    { key: 'targets', label: 'Targets' },
    { key: 'recent', label: 'Recent' },
    { key: 'alpha', label: 'A-Z' },
    { key: 'completion', label: 'Done%' },
  ];

  const toggleExpanded = (seedName: string) => {
    setExpandedSeeds((prev) => {
      const next = new Set(prev);
      if (next.has(seedName)) next.delete(seedName); else next.add(seedName);
      return next;
    });
  };

  return (
    <div className="flex-1 overflow-y-auto space-y-2 p-1">
      {/* Header row: title + compact toggle + add seed */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Seeds
          <span className="ml-1 text-xs font-normal text-gray-400">{filteredSeeds.length}/{seeds.length}</span>
        </h3>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setCompactMode(!compactMode)}
            className={`p-1 rounded transition-colors ${compactMode
              ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400'
              : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700'}`}
            title={compactMode ? 'Grid view' : 'List view'}
            aria-label={compactMode ? 'Switch to grid view' : 'Switch to list view'}
          >
            {compactMode ? <LayoutGrid className="w-3.5 h-3.5" /> : <LayoutList className="w-3.5 h-3.5" />}
          </button>
          <button
            onClick={onOpenCaptureSnapshot}
            className="flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded hover:bg-blue-100 transition-colors"
            title="Open capture flow"
          >
            <Plus className="w-3 h-3" /> Add
          </button>
        </div>
      </div>

      {/* Unified control row: search + status tabs + sort */}
      <div className="flex items-center gap-1.5 flex-wrap">
        {/* Search */}
        <div className="relative w-32">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search..."
            className="w-full pl-6 pr-2 py-1 text-[11px] rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-400"
          />
        </div>

        {/* Status tabs */}
        <div className="flex gap-0.5" role="tablist" aria-label="Seed status filter">
          {statusTabs.map((tab) => (
            <button
              key={tab.key}
              role="tab"
              aria-selected={statusFilter === tab.key}
              onClick={() => setStatusFilter(tab.key)}
              className={`px-1.5 py-0.5 text-[10px] font-medium rounded transition-colors ${statusFilter === tab.key
                ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300'
                : 'text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'}`}
            >
              {tab.label}
              {tab.count > 0 && <span className="ml-0.5 opacity-60">{tab.count}</span>}
            </button>
          ))}
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Sort */}
        <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-gray-800 rounded p-0.5">
          {sortOptions.map((opt) => {
            const isActive = sortKey === opt.key;
            const arrow = isActive ? (sortAsc ? '↑' : '↓') : '';
            return (
              <button
                key={opt.key}
                onClick={() => {
                  if (isActive) setSortAsc(!sortAsc);
                  else { setSortKey(opt.key); setSortAsc(false); }
                }}
                className={`px-1.5 py-0.5 text-[10px] font-medium rounded transition-colors ${isActive
                  ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700'}`}
              >
                {opt.label}{arrow}
              </button>
            );
          })}
        </div>
      </div>

      {/* Seed List */}
      {loading && seeds.length === 0 ? (
        <div className="flex items-center justify-center h-24">
          <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
        </div>
      ) : filteredSeeds.length === 0 ? (
        <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-6 text-center">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {seeds.length === 0
              ? 'No seeds yet. Run a following analysis or add a seed.'
              : `No seeds match "${searchQuery || statusFilter}"`}
          </p>
        </div>
      ) : compactMode ? (
        /* List (compact) mode — full-width rows with bio */
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden divide-y divide-gray-100 dark:divide-gray-800">
          {filteredSeeds.map((seed) => {
            const seedKey = seed.seed.toLowerCase();
            const exec = seedExecutionMap.get(seedKey) || null;
            const status = exec?.status || 'idle';
            const isExpanded = expandedSeeds.has(seed.seed);
            const completion = seed.target_count > 0 ? Math.round((seed.visited_count / seed.target_count) * 100) : 0;
            const seedDebug = (seedKey === debugSeed) ? igDebug : undefined;

            const badgeClass =
              status === 'running' ? 'bg-blue-500' :
                status === 'pending' ? 'bg-amber-500' :
                  status === 'failed' ? 'bg-red-500' :
                    completion >= 100 ? 'bg-green-500' :
                      'bg-gray-300 dark:bg-gray-600';

            return (
              <div key={seed.seed}>
                <button
                  onClick={() => isExpanded ? toggleExpanded(seed.seed) : onViewInsights(seed.seed)}
                  onContextMenu={(e) => { e.preventDefault(); toggleExpanded(seed.seed); }}
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
                >
                  <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${badgeClass}`} />
                  <span className="text-xs font-semibold text-gray-900 dark:text-gray-100 w-28 truncate flex-shrink-0">
                    @{seed.seed}
                  </span>
                  <span className="text-[10px] text-gray-500 tabular-nums flex-shrink-0 w-20">
                    {seed.target_count}{seed.expected_count ? `/${seed.expected_count}` : ''}
                  </span>
                  {seed.target_count > 0 && (
                    <span className={`text-[10px] tabular-nums flex-shrink-0 w-10 ${completion >= 100 ? 'text-green-600 dark:text-green-400' : 'text-gray-400'}`}>
                      {completion}%
                    </span>
                  )}
                  {seed.bio && (
                    <span className="text-[10px] text-gray-400 truncate min-w-0 flex-1">
                      {seed.bio}
                    </span>
                  )}
                  <span className={`text-[10px] text-gray-400 flex-shrink-0 transition-transform ${isExpanded ? 'rotate-90' : ''}`}>▸</span>
                </button>
                {isExpanded && (
                  <div className="px-2 pb-2">
                    <SeedCard
                      workspaceId={workspaceId}
                      seed={seed}
                      onViewInsights={onViewInsights}
                      onReCrawl={onReCrawl}
                      onRemove={handleRemove}
                      seedExecution={exec}
                      igDebug={seedDebug || undefined}
                      apiUrl={apiUrl}
                      onRerun={(executionId, overrideInputs) => handleSeedRerun(seed.seed, executionId, overrideInputs)}
                      onCancel={(executionId) => handleSeedCancel(seed.seed, executionId)}
                      rerunBusyId={rerunBusyId}
                      cancelBusyId={cancelBusyId}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        /* Grid (card) mode — 2 columns */
        <div className="grid grid-cols-2 gap-2">
          {filteredSeeds.map((seed) => {
            const seedKey = seed.seed.toLowerCase();
            const exec = seedExecutionMap.get(seedKey) || null;
            const seedDebug = (seedKey === debugSeed) ? igDebug : undefined;

            return (
              <SeedCard
                workspaceId={workspaceId}
                key={seed.seed}
                seed={seed}
                onViewInsights={onViewInsights}
                onReCrawl={onReCrawl}
                onRemove={handleRemove}
                seedExecution={exec}
                igDebug={seedDebug || undefined}
                apiUrl={apiUrl}
                onRerun={(executionId, overrideInputs) => handleSeedRerun(seed.seed, executionId, overrideInputs)}
                onCancel={(executionId) => handleSeedCancel(seed.seed, executionId)}
                rerunBusyId={rerunBusyId}
                cancelBusyId={cancelBusyId}
              />
            );
          })}
        </div>
      )}

      {/* Connected Accounts */}
      <details className="group">
        <summary className="cursor-pointer text-sm font-semibold text-gray-900 dark:text-gray-100 list-none flex items-center gap-1">
          <span className="text-xs text-gray-400 group-open:rotate-90 transition-transform">▶</span>
          Connected Accounts ({filteredConnectedAccounts.length})
        </summary>
        <div className="mt-2">
          <ConnectedAccountsCard accounts={filteredConnectedAccounts} />
        </div>
      </details>
    </div>
  );
}
