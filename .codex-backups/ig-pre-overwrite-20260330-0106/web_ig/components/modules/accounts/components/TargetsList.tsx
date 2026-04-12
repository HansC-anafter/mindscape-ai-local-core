// @ts-nocheck
/* eslint-disable */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Instagram } from 'lucide-react';

import type { DiscoveredAccount } from '../types';
import { formatCount, getAvatarUrl } from '../utils';

function getInstagramProfileUrl(account: any): string {
  return `https://www.instagram.com/${account.handle}/`;
}

function normalizeHandle(handle: string | null | undefined): string {
  return (handle || '').replace(/^@/, '').trim().toLowerCase();
}

let _savedListScrollTop = 0;

const LOAD_MORE_THRESHOLD_PX = 400;
const LOAD_MORE_COOLDOWN_MS = 500;

export function TargetsList(props: any) {
  const { apiUrl, targets, onSelect, loadMore, hasMore, loadingMore } = props;
  const scrollerRef = useRef<any>(null);
  const itemRefs = useRef(new Map<string, HTMLDivElement>());
  const targetsRef = useRef(targets);
  const onSelectRef = useRef(onSelect);
  const loadMoreRef = useRef(loadMore);
  const hasMoreRef = useRef(hasMore);
  const loadingMoreRef = useRef(loadingMore);
  const scrollTopRef = useRef(_savedListScrollTop);
  const lastLoadMoreRef = useRef(0);
  const highlightTimeoutRef = useRef<number | null>(null);
  const [highlightHandle, setHighlightHandle] = useState<string | null>(null);

  targetsRef.current = targets;
  onSelectRef.current = onSelect;
  loadMoreRef.current = loadMore;
  hasMoreRef.current = hasMore;
  loadingMoreRef.current = loadingMore;

  const maybeLoadMore = useCallback(() => {
    const element = scrollerRef.current as HTMLDivElement | null;
    if (!element || !loadMoreRef.current || !hasMoreRef.current || loadingMoreRef.current) return;

    const remaining = element.scrollHeight - element.scrollTop - element.clientHeight;
    if (remaining > LOAD_MORE_THRESHOLD_PX) return;

    const now = Date.now();
    if (now - lastLoadMoreRef.current < LOAD_MORE_COOLDOWN_MS) return;

    lastLoadMoreRef.current = now;
    loadMoreRef.current();
  }, []);

  useEffect(() => {
    return () => {
      _savedListScrollTop = scrollTopRef.current;
    };
  }, []);

  useEffect(() => {
    const rafId = window.requestAnimationFrame(() => {
      const element = scrollerRef.current as HTMLDivElement | null;
      if (!element) return;
      if (_savedListScrollTop > 0) {
        element.scrollTop = _savedListScrollTop;
        scrollTopRef.current = _savedListScrollTop;
      }
      maybeLoadMore();
    });

    return () => window.cancelAnimationFrame(rafId);
  }, []);

  useEffect(() => {
    const rafId = window.requestAnimationFrame(() => {
      maybeLoadMore();
    });
    return () => window.cancelAnimationFrame(rafId);
  }, [targets.length, hasMore, loadingMore, maybeLoadMore]);

  useEffect(() => {
    const handler = (e: CustomEvent<string | { handle: string; seed?: string | null }>) => {
      const detail = e.detail;
      const handle = typeof detail === 'string' ? detail : detail?.handle;
      const normalizedHandle = normalizeHandle(handle);
      if (!normalizedHandle) return;

      const targetNode = itemRefs.current.get(normalizedHandle);
      if (!targetNode) return;

      targetNode.scrollIntoView({ block: 'center', behavior: 'smooth' });
      setHighlightHandle(normalizedHandle);
      if (highlightTimeoutRef.current != null) {
        window.clearTimeout(highlightTimeoutRef.current);
      }
      highlightTimeoutRef.current = window.setTimeout(() => {
        setHighlightHandle(null);
        highlightTimeoutRef.current = null;
      }, 2500);
    };

    window.addEventListener('ig:scroll-to-account', handler as EventListener);
    return () => {
      window.removeEventListener('ig:scroll-to-account', handler as EventListener);
      if (highlightTimeoutRef.current != null) {
        window.clearTimeout(highlightTimeoutRef.current);
      }
    };
  }, []);

  const handleSelect = useCallback((account: DiscoveredAccount) => {
    _savedListScrollTop = scrollTopRef.current;
    onSelectRef.current(account);
  }, []);

  const handleScroll = useCallback((event: any) => {
    const element = event.currentTarget as HTMLDivElement;
    scrollTopRef.current = element.scrollTop;
    maybeLoadMore();
  }, []);

  const setItemRef = useCallback((handle: string, node: HTMLDivElement | null) => {
    const normalizedHandle = normalizeHandle(handle);
    if (!normalizedHandle) return;

    if (node) {
      itemRefs.current.set(normalizedHandle, node);
    } else {
      itemRefs.current.delete(normalizedHandle);
    }
  }, []);

  return (
    <div
      ref={scrollerRef}
      className="h-full overflow-y-auto pr-1"
      onScroll={handleScroll}
    >
      <div className="space-y-2 pb-4">
        {targets.map((account: DiscoveredAccount, index: number) => {
          const normalizedHandle = normalizeHandle(account.handle);
          const key = normalizedHandle || account.account_id || `target-${index}`;

          return (
            <div
              key={key}
              ref={(node) => setItemRef(account.handle, node)}
              onClick={() => handleSelect(account)}
              className={`relative p-4 bg-white dark:bg-gray-800 rounded-lg border cursor-pointer transition-colors ${
                highlightHandle === normalizedHandle
                  ? 'border-blue-500 ring-2 ring-blue-400/50'
                  : 'border-gray-200 dark:border-gray-700 hover:border-blue-500 dark:hover:border-blue-500'
              }`}
            >
              <a
                href={getInstagramProfileUrl(account)}
                target="_blank"
                rel="noreferrer"
                onClick={(e: any) => e.stopPropagation()}
                className="absolute top-3 right-3 p-1.5 rounded-md bg-white/80 dark:bg-gray-900/40 border border-gray-200 dark:border-gray-700 hover:bg-white dark:hover:bg-gray-900"
                title="Open Instagram profile"
                aria-label="Open Instagram profile"
              >
                <Instagram className="w-4 h-4 text-gray-700 dark:text-gray-200" />
              </a>

              <div className="flex items-center gap-3">
                <img
                  src={getAvatarUrl(account.handle, account.fetched_at)}
                  alt={account.handle}
                  className="w-10 h-10 rounded-full"
                  onError={(e) => {
                    const img = e.target as HTMLImageElement;
                    if (img.dataset.fallbackApplied === '1') return;
                    img.dataset.fallbackApplied = '1';
                    img.src = `https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(account.handle || 'IG')}&backgroundColor=6366f1`;
                  }}
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      @{account.handle}
                    </h3>
                    {account.is_verified && (
                      <span className="text-xs text-blue-500">Verified</span>
                    )}
                  </div>
                  {account.name && (
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {account.name}
                    </p>
                  )}
                  {account.bio && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2 mt-1">
                      {account.bio}
                    </p>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400 mt-2">
                <span>Followers: {account.follower_count !== undefined ? formatCount(account.follower_count) : '—'}</span>
                <span>Following: {account.following_count !== undefined ? formatCount(account.following_count) : '—'}</span>
                <span>Posts: {account.post_count !== undefined ? formatCount(account.post_count) : '—'}</span>
              </div>
            </div>
          );
        })}
      </div>

      {loadingMore && (
        <div className="py-4 text-center text-xs text-gray-500 dark:text-gray-400">
          Loading more...
        </div>
      )}
    </div>
  );
}
