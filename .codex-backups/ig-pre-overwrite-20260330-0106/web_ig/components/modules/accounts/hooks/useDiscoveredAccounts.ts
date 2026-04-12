import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MindscapeAPIClient } from '@/api/client';

import type { DiscoveredAccount } from '../types';
import { fetchTargets } from '../api';

const TARGETS_PAGE_SIZE = 50;
const TARGETS_REQUEST_TIMEOUT_MS = 20_000;
const TARGETS_SEARCH_DEBOUNCE_MS = 350;

type TargetsRequestError = Error & {
  status?: number;
  detail?: string;
};

function createTargetsRequestError(status: number, detail?: string): TargetsRequestError {
  const suffix = detail ? `: ${detail}` : '';
  const error = new Error(`Targets request failed (${status})${suffix}`) as TargetsRequestError;
  error.status = status;
  error.detail = detail;
  return error;
}

function createTargetsTimeoutError(label: string): TargetsRequestError {
  return new Error(`${label} timeout`) as TargetsRequestError;
}

function createTargetsAbortError(label: string): TargetsRequestError {
  return new Error(`${label} aborted`) as TargetsRequestError;
}

function isTargetsAbortError(error: unknown): boolean {
  return error instanceof Error && error.message.toLowerCase().includes('aborted');
}

function toTargetsLoadMessage(error: unknown): string {
  const status = typeof (error as any)?.status === 'number' ? (error as any).status : null;
  const detail = typeof (error as any)?.detail === 'string' ? (error as any).detail.trim() : '';
  const message = error instanceof Error ? error.message.toLowerCase() : '';

  if (status === 404) {
    return 'Targets API unavailable. Confirm the IG pack is installed and the backend restarted.';
  }
  if (status === 401 || status === 403) {
    return 'Targets request was denied. Check auth and workspace access.';
  }
  if (status === 500) {
    return detail
      ? `Targets API failed on the backend: ${detail}`
      : 'Targets API failed on the backend. Check IG backend logs and migrations.';
  }
  if (message.includes('timeout')) {
    return 'Targets request timed out. Check IG insights query performance and retry after the latest backend optimizations are deployed.';
  }
  return detail ? `Failed to load targets: ${detail}` : 'Failed to load targets.';
}

/**
 * Hook that fetches discovered accounts from ig_accounts_flat DB table
 * via the /api/v1/ig/insights/targets endpoint.
 *
 * Architecture:
 * - Append-only pages cache: loaded pages are never silently replaced.
 * - Virtuoso drives pagination via `loadMore` (called by `endReached`).
 * - SSE/polling calls `refreshTotal` which only updates the total count
 *   without touching loaded data — prevents scroll snap-back.
 * - `reset` is the sole full-clear trigger (filter change / execution end).
 */
export function useDiscoveredAccounts(params: {
  apiUrl: string;
  workspaceId: string;
  seed?: string;
  sourceHandle?: string;
  search?: string;
  enabled?: boolean;
}) {
  const { apiUrl, workspaceId, seed, sourceHandle, search, enabled = true } = params;
  const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);
  const normalizedSearch = (search || '').trim();

  // Pages cache: each entry is one server page (up to TARGETS_PAGE_SIZE items)
  const [pages, setPages] = useState<DiscoveredAccount[][]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [debouncedSearch, setDebouncedSearch] = useState(normalizedSearch);

  // Guards
  const inFlightRef = useRef(false);
  const requestKeyRef = useRef('');
  const activeRequestControllerRef = useRef<AbortController | null>(null);

  // Derived: stable flat array of all loaded accounts
  const allAccounts = useMemo(() => pages.flat(), [pages]);
  const hasMore = allAccounts.length < total;

  // Keep refs in sync for closures
  const pagesRef = useRef(pages);
  const totalRef = useRef(total);
  useEffect(() => { pagesRef.current = pages; }, [pages]);
  useEffect(() => { totalRef.current = total; }, [total]);
  useEffect(() => {
    const timer = window.setTimeout(
      () => setDebouncedSearch(normalizedSearch),
      normalizedSearch ? TARGETS_SEARCH_DEBOUNCE_MS : 0
    );
    return () => window.clearTimeout(timer);
  }, [normalizedSearch]);
  useEffect(() => () => activeRequestControllerRef.current?.abort(), []);

  const isSearchActive = debouncedSearch.length > 0;

  const buildRequestKey = useCallback(
    () => `${apiUrl}::${workspaceId}::${seed || ''}::${sourceHandle || ''}::${debouncedSearch}`,
    [apiUrl, workspaceId, seed, sourceHandle, debouncedSearch]
  );

  const mapTargetToAccount = (t: any): DiscoveredAccount => ({
    account_id: t.handle,
    handle: t.handle,
    name: t.name || undefined,
    bio: t.bio || undefined,
    profile_picture_url: t.profile_picture_url || undefined,
    follower_count: t.follower_count ?? undefined,
    following_count: t.following_count ?? undefined,
    post_count: t.post_count ?? undefined,
    external_url: t.external_url || undefined,
    is_verified: t.is_verified ?? false,
    public_email: t.public_email || undefined,
    public_phone_number: t.public_phone_number || undefined,
    business_address_json: t.business_address_json || undefined,
    fetched_at: t.captured_at || '',
    source: 'following_list',
    sources: [
      {
        source_account_handle: t.source_handle || undefined,
        source_profile_ref: t.source_profile_ref || undefined,
        target_seed: t.seed || undefined,
        captured_at: t.captured_at || undefined,
      },
    ],
    category: t.category || undefined,
  });

  const fetchPage = useCallback(
    async (offset: number, signal?: AbortSignal) => {
      if (!enabled) {
        return { accounts: [], total: totalRef.current };
      }
      const requestKey = `${Date.now()}:${offset}:${Math.random().toString(36).slice(2, 8)}`;
      const response = await fetchTargets(client, {
        workspace_id: workspaceId,
        seed: seed || undefined,
        source_handle: sourceHandle || undefined,
        search: debouncedSearch || undefined,
        limit: TARGETS_PAGE_SIZE,
        offset,
        request_key: requestKey,
        signal,
      });

      if (!response.ok) {
        let detail = '';
        try {
          const payload = await response.clone().json();
          detail = typeof payload?.detail === 'string' ? payload.detail : '';
        } catch {
          // ignore parse failures
        }
        throw createTargetsRequestError(response.status, detail);
      }

      const data = await response.json();
      const accounts: DiscoveredAccount[] = (data.targets || []).map(mapTargetToAccount);
      return { accounts, total: data.total as number };
    },
    [client, enabled, workspaceId, seed, sourceHandle, debouncedSearch]
  );

  const fetchPageWithTimeout = useCallback(
    async (offset: number, label: string) => {
      activeRequestControllerRef.current?.abort();
      const controller = new AbortController();
      activeRequestControllerRef.current = controller;
      let timedOut = false;
      const timeoutId = window.setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, TARGETS_REQUEST_TIMEOUT_MS);

      try {
        return await fetchPage(offset, controller.signal);
      } catch (error) {
        if (timedOut) {
          throw createTargetsTimeoutError(label);
        }
        if (error instanceof Error && error.name === 'AbortError') {
          throw createTargetsAbortError(label);
        }
        throw error;
      } finally {
        window.clearTimeout(timeoutId);
        if (activeRequestControllerRef.current === controller) {
          activeRequestControllerRef.current = null;
        }
      }
    },
    [fetchPage]
  );

  // ── reset: clear cache and fetch page 0 ──
  // Called on filter change and execution completion.
  const reset = useCallback(async () => {
    if (!enabled) return;
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    const key = buildRequestKey();
    requestKeyRef.current = key;
    setError(null);
    setLoading(true);
    try {
      const { accounts, total: newTotal } = await fetchPageWithTimeout(0, 'initial targets request');
      if (key !== requestKeyRef.current) return;
      setPages(accounts.length > 0 ? [accounts] : []);
      setTotal(newTotal);
    } catch (err) {
      if (key !== requestKeyRef.current || isTargetsAbortError(err)) {
        return;
      }
      if (key === requestKeyRef.current) {
        setError(toTargetsLoadMessage(err));
      }
    } finally {
      if (key === requestKeyRef.current) {
        setLoading(false);
      }
      inFlightRef.current = false;
    }
  }, [enabled, fetchPageWithTimeout, buildRequestKey]);

  // ── loadMore: append next page to cache ──
  // Called by Virtuoso endReached.
  const loadMore = useCallback(async () => {
    if (!enabled) return;
    if (inFlightRef.current) return;
    const currentLength = pagesRef.current.flat().length;
    if (currentLength >= totalRef.current) return;
    inFlightRef.current = true;
    const key = requestKeyRef.current;
    setLoadingMore(true);
    try {
      const { accounts, total: newTotal } = await fetchPageWithTimeout(currentLength, 'loadMore');
      if (key !== requestKeyRef.current) return;
      if (accounts.length === 0) {
        setTotal(currentLength);
        return;
      }
      const existingHandles = new Set(pagesRef.current.flat().map(a => a.handle));
      const uniqueAccounts = accounts.filter(a => !existingHandles.has(a.handle));
      if (uniqueAccounts.length > 0) {
        setPages(prev => [...prev, uniqueAccounts]);
      } else if (accounts.length > 0) {
        setTotal(currentLength);
        return;
      }
      setTotal(newTotal);
    } catch {
      // swallow — timeout or network error
    } finally {
      if (key === requestKeyRef.current) {
        setLoadingMore(false);
      }
      inFlightRef.current = false;
    }
  }, [enabled, fetchPageWithTimeout]);

  // ── refreshTotal: only update total count ──
  // Called as fallback polling. Never touches pages cache.
  const refreshTotal = useCallback(async () => {
    if (!enabled || isSearchActive) return;
    try {
      const response = await fetchTargets(client, {
        workspace_id: workspaceId,
        seed: seed || undefined,
        source_handle: sourceHandle || undefined,
        search: debouncedSearch || undefined,
        limit: 1,
        offset: 0,
      });
      if (!response.ok) return;
      const data = await response.json();
      const newTotal = data.total as number;
      if (newTotal !== totalRef.current) {
        setTotal(newTotal);
      }
    } catch {
      // Non-critical — swallow silently
    }
  }, [client, enabled, workspaceId, seed, sourceHandle, debouncedSearch, isSearchActive]);

  // ── refreshData: merge-update page 0 during SSE events ──
  // Uses its own guard so it never blocks loadMore's pagination.
  // Yields to loadMore: if inFlightRef is held, refreshData skips.
  const refreshBusyRef = useRef(false);
  const refreshDataLastRef = useRef(0);
  const REFRESH_DATA_MIN_INTERVAL = 8_000;
  const refreshData = useCallback(async () => {
    if (!enabled || isSearchActive) return;
    if (refreshBusyRef.current || inFlightRef.current) return;
    const now = Date.now();
    if (now - refreshDataLastRef.current < REFRESH_DATA_MIN_INTERVAL) return;
    refreshDataLastRef.current = now;
    refreshBusyRef.current = true;
    const key = requestKeyRef.current;
    try {
      const currentPages = pagesRef.current;
      if (currentPages.length === 0) {
        // No pages loaded yet — poll total to see if data appeared
        refreshBusyRef.current = false;
        try {
          const { total: newTotal } = await fetchPageWithTimeout(0, 'refreshData');
          if (newTotal > 0 && newTotal !== totalRef.current) {
            setTotal(newTotal);
            void reset();
          }
        } catch { /* swallow */ }
        return;
      }

      const { accounts: freshPage0, total: newTotal } = await fetchPageWithTimeout(0, 'refreshData');
      if (key !== requestKeyRef.current) return;

      if (newTotal !== totalRef.current) {
        setTotal(newTotal);
      }

      const oldPage0 = currentPages[0] || [];
      const changed =
        freshPage0.length !== oldPage0.length ||
        freshPage0.some((a, i) => {
          const old = oldPage0[i];
          if (!old) return true;
          return (
            a.handle !== old.handle ||
            a.follower_count !== old.follower_count ||
            a.bio !== old.bio ||
            a.is_verified !== old.is_verified
          );
        });

      if (changed) {
        setPages(prev => {
          const updated = [...prev];
          updated[0] = freshPage0;
          return updated;
        });
      }
    } catch {
      // swallow — timeout or network error
    } finally {
      refreshBusyRef.current = false;
    }
  }, [enabled, fetchPageWithTimeout, reset, isSearchActive]);

  // ── refreshSingleAccount: targeted card update for visit_pages ──
  // Fetches one account by handle and patches it in-place in the pages cache.
  const refreshSingleAccount = useCallback(async (handle: string) => {
    if (!enabled) return;
    const normalizedHandle = (handle || '').replace(/^@/, '').trim().toLowerCase();
    if (!normalizedHandle) return;
    try {
      const response = await fetchTargets(client, {
        workspace_id: workspaceId,
        seed: seed || undefined,
        source_handle: sourceHandle || undefined,
        handle: normalizedHandle,
        limit: 1,
        offset: 0,
      });
      if (!response.ok) return;
      const data = await response.json();
      const rawTargets = data.targets || [];
      if (rawTargets.length === 0) return;
      const fresh = mapTargetToAccount(rawTargets[0]);
      const freshHandle = (fresh.handle || '').toString().trim().toLowerCase();
      if (!freshHandle) return;
      // Patch in-place: only touch the page that contains this handle
      setPages(prev => {
        for (let pi = 0; pi < prev.length; pi++) {
          const idx = prev[pi].findIndex(
            (a) => (a.handle || '').toString().trim().toLowerCase() === freshHandle
          );
          if (idx !== -1) {
            const newPage = [...prev[pi]];
            newPage[idx] = fresh;
            const updated = [...prev];
            updated[pi] = newPage;
            return updated;
          }
        }
        return prev;
      });
    } catch {
      // Non-critical — swallow
    }
  }, [client, enabled, workspaceId, seed, sourceHandle]);

  // ── Auto-reset on filter parameter changes ──
  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      setLoadingMore(false);
      setError(null);
      inFlightRef.current = false;
      return;
    }
    const key = buildRequestKey();
    if (key === requestKeyRef.current && pagesRef.current.length > 0) return;
    requestKeyRef.current = key;
    inFlightRef.current = false;
    setPages([]);
    setTotal(0);
    setError(null);
    void reset();
  }, [enabled, buildRequestKey, reset]);

  return {
    allAccounts,
    total,
    loading,
    loadingMore,
    error,
    hasMore,
    loadMore,
    refreshTotal,
    refreshData,
    refreshSingleAccount,
    reset,
  };
}

export const ACCOUNTS_PAGE_SIZE = TARGETS_PAGE_SIZE;
