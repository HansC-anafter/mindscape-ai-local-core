// @ts-nocheck
/* eslint-disable */
import React, { memo, useCallback, useRef, useEffect, useState } from 'react';
import { Instagram, Users } from 'lucide-react';

import type { DiscoveredAccount } from '../types';
import { formatCount, getAvatarUrl, getProxiedImageUrl } from '../utils';
import { PostPreviewPopover } from './PostPreviewPopover';

function getInstagramProfileUrl(account: any): string {
  return `https://www.instagram.com/${account.handle}/`;
}

function normalizeHandle(handle: string | null | undefined): string {
  return (handle || '').replace(/^@/, '').trim().toLowerCase();
}

// Memoized account card to prevent re-renders from cancelling image loads
const AccountCard = memo(function AccountCard({
  account,
  onSelect,
  getTagsForHandle,
  highlighted,
}: {
  account: DiscoveredAccount;
  onSelect: (account: DiscoveredAccount) => void;
  getTagsForHandle: (handle: string, tags?: string[]) => string[];
  highlighted?: boolean;
}) {
  // Primary: proxy CDN URL if available (same strategy as detail page)
  // Fallback: avatar-proxy endpoint (handles cache / DB lookup / DiceBear / background fetch)
  const proxiedCdn = getProxiedImageUrl('', account.profile_picture_url);
  const avatarProxyUrl = getAvatarUrl(account.handle, account.fetched_at);
  const primaryUrl = proxiedCdn || avatarProxyUrl;
  const [imgSrc, setImgSrc] = useState(primaryUrl);

  const cardRef = useRef<HTMLDivElement>(null);
  const [isHovered, setIsHovered] = useState(false);
  const hoverTimeoutRef = useRef<number | null>(null);

  const handleMouseEnter = useCallback(() => {
    if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
    hoverTimeoutRef.current = window.setTimeout(() => {
      setIsHovered(true);
    }, 400); // 400ms debounce
  }, []);

  const handleMouseLeave = useCallback(() => {
    if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
    setIsHovered(false);
  }, []);

  useEffect(() => {
    const nextProxied = getProxiedImageUrl('', account.profile_picture_url);
    const nextAvatar = getAvatarUrl(account.handle, account.fetched_at);
    setImgSrc(nextProxied || nextAvatar);
  }, [account.handle, account.fetched_at, account.profile_picture_url]);

  return (
    <>
      <div
        ref={cardRef}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        onClick={() => onSelect(account)}
        onKeyDown={(e: any) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onSelect(account);
          }
        }}
        role="button"
        tabIndex={0}
        className={`relative text-left p-4 bg-white dark:bg-gray-800 rounded-lg border transition-all cursor-pointer h-[180px] overflow-hidden ${highlighted
          ? 'border-blue-500 ring-2 ring-blue-400/50 shadow-lg shadow-blue-500/20'
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
            src={imgSrc}
            alt={account.handle}
            className="w-12 h-12 rounded-full flex-shrink-0"
            loading="lazy"
            onError={(e: any) => {
              // Chain: proxied CDN → avatar proxy → (DiceBear via avatar proxy)
              if (proxiedCdn && imgSrc === proxiedCdn) {
                setImgSrc(avatarProxyUrl);
              }
            }}
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <div className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
                @{account.handle}
              </div>
              {account.is_verified && <span className="text-xs text-blue-500 flex-shrink-0">Verified</span>}
            </div>
            {account.name && (
              <div className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">{account.name}</div>
            )}
          </div>
        </div>

        {(account.bio || (account.follower_count !== undefined)) && (
          <div className="mt-2.5 space-y-2">
            {account.bio && (
              <div className="text-[11px] leading-relaxed text-gray-600 dark:text-gray-300 line-clamp-2 italic">
                {account.bio}
              </div>
            )}

            <div className="flex items-center gap-2 overflow-hidden whitespace-nowrap text-[10px] text-gray-500 dark:text-gray-400">
              <span>{account.follower_count !== undefined ? formatCount(account.follower_count) : '—'} <span className="opacity-70">Followers</span></span>
              <span className="opacity-30">|</span>
              <span>{account.following_count !== undefined ? formatCount(account.following_count) : '—'} <span className="opacity-70">Following</span></span>
              <span className="opacity-30">|</span>
              <span>{account.post_count !== undefined ? formatCount(account.post_count) : '—'} <span className="opacity-70">Posts</span></span>
            </div>
          </div>
        )}

        <div className="mt-2.5 flex flex-col gap-1.5">
          {(account.sources && account.sources.length > 0) && (
            <div className="flex flex-wrap gap-1">
              {account.sources
                .map((s: any) => s.source_account_handle ? `@${s.source_account_handle}` : 'Unknown')
                .filter((v: any, idx: number, arr: any[]) => arr.indexOf(v) === idx)
                .slice(0, 3)
                .map((label: string) => (
                  <span
                    key={label}
                    className="px-1.5 py-0.5 text-[10px] bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded ring-1 ring-inset ring-gray-200/50 dark:ring-gray-600/50"
                  >
                    {label}
                  </span>
                ))}
            </div>
          )}

          {getTagsForHandle(account.handle, account.tags).length > 0 && (
            <div className="flex flex-wrap gap-1">
              {getTagsForHandle(account.handle, account.tags).slice(0, 4).map((t: string) => (
                <span
                  key={t}
                  className="px-1.5 py-0.5 text-[10px] bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 rounded ring-1 ring-inset ring-blue-200/30 dark:ring-blue-800/20"
                >
                  {t}
                </span>
              ))}
            </div>
          )}
        </div>

      </div>
      <PostPreviewPopover
        account={account}
        triggerRef={cardRef}
        isOpen={isHovered}
      />
    </>
  );
});

let _savedGridScrollTop = 0;

const LOAD_MORE_THRESHOLD_PX = 600;
const LOAD_MORE_COOLDOWN_MS = 500;

export function TargetsGrid(props: {
  apiUrl: string;
  targets: DiscoveredAccount[];
  getTagsForHandle: (handle: string, tags?: string[]) => string[];
  onSelect: (account: DiscoveredAccount) => void;
  loadMore?: () => void;
  hasMore?: boolean;
  loadingMore?: boolean;
}) {
  const { targets, onSelect, getTagsForHandle, loadMore, hasMore, loadingMore } = props;
  const scrollerRef = useRef<any>(null);
  const itemRefs = useRef(new Map<string, HTMLDivElement>());
  const [highlightHandle, setHighlightHandle] = useState<string | null>(null);
  const targetsRef = useRef(targets);
  const onSelectRef = useRef(onSelect);
  const getTagsForHandleRef = useRef(getTagsForHandle);
  const loadMoreRef = useRef(loadMore);
  const hasMoreRef = useRef(hasMore);
  const loadingMoreRef = useRef(loadingMore);
  const scrollTopRef = useRef(_savedGridScrollTop);
  const lastLoadMoreRef = useRef(0);
  const highlightTimeoutRef = useRef<number | null>(null);

  targetsRef.current = targets;
  onSelectRef.current = onSelect;
  getTagsForHandleRef.current = getTagsForHandle;
  loadMoreRef.current = loadMore;
  hasMoreRef.current = hasMore;
  loadingMoreRef.current = loadingMore;

  const maybeLoadMore = useCallback(() => {
    const element = scrollerRef.current as HTMLDivElement | null;
    if (!element || !loadMoreRef.current || !hasMoreRef.current || loadingMoreRef.current) {
      return;
    }

    const remaining = element.scrollHeight - element.scrollTop - element.clientHeight;
    if (remaining > LOAD_MORE_THRESHOLD_PX) return;

    const now = Date.now();
    if (now - lastLoadMoreRef.current < LOAD_MORE_COOLDOWN_MS) return;

    lastLoadMoreRef.current = now;
    loadMoreRef.current();
  }, []);

  // Listen for scroll-to-account events
  useEffect(() => {
    const handler = (e: CustomEvent<string | { handle: string; seed?: string | null }>) => {
      const detail = e.detail;
      const handle = typeof detail === 'string' ? detail : detail?.handle;
      const normalizedHandle = normalizeHandle(handle);
      const currentTargets = targetsRef.current;
      if (!normalizedHandle || !currentTargets?.length) return;
      const idx = currentTargets.findIndex((t: DiscoveredAccount) =>
        normalizeHandle(t.handle) === normalizedHandle
      );
      if (idx < 0) return;

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

  useEffect(() => {
    return () => {
      _savedGridScrollTop = scrollTopRef.current;
    };
  }, []);

  useEffect(() => {
    const rafId = window.requestAnimationFrame(() => {
      const element = scrollerRef.current as HTMLDivElement | null;
      if (!element) return;
      if (_savedGridScrollTop > 0) {
        element.scrollTop = _savedGridScrollTop;
        scrollTopRef.current = _savedGridScrollTop;
      }
      maybeLoadMore();
    });

    return () => window.cancelAnimationFrame(rafId);
  }, [maybeLoadMore]);

  useEffect(() => {
    const rafId = window.requestAnimationFrame(() => {
      maybeLoadMore();
    });
    return () => window.cancelAnimationFrame(rafId);
  }, [targets.length, hasMore, loadingMore, maybeLoadMore]);

  const stableOnSelect = useCallback((account: DiscoveredAccount) => {
    _savedGridScrollTop = scrollTopRef.current;
    onSelectRef.current(account);
  }, []);

  const stableGetTagsForHandle = useCallback((handle: string, tags?: string[]) => {
    return getTagsForHandleRef.current(handle, tags);
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
  }, [stableOnSelect, stableGetTagsForHandle]);

  return (
    <div
      ref={scrollerRef}
      className="h-full overflow-y-auto pr-1"
      onScroll={handleScroll}
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pb-4">
        {targets.map((account: DiscoveredAccount, index: number) => {
          const normalizedHandle = normalizeHandle(account.handle);
          const key = normalizedHandle || account.account_id || `target-${index}`;

          return (
            <div
              key={key}
              ref={(node) => setItemRef(account.handle, node)}
              className="min-w-0"
            >
              <AccountCard
                account={account}
                onSelect={stableOnSelect}
                getTagsForHandle={stableGetTagsForHandle}
                highlighted={highlightHandle === normalizedHandle}
              />
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
