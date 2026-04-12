import React from 'react';

import type { DiscoveredAccount } from '../types';
import type { FilterOption } from '../selectors';
import { formatCount } from '../utils';

type AnalyticsMetric = 'followers' | 'following' | 'posts';

export function AccountsAnalyticsPanel(props: {
  analyticsMetric: AnalyticsMetric;
  onAnalyticsMetricChange: (value: AnalyticsMetric) => void;
  sourceFilterKey: string;
  onSourceFilterKeyChange: (value: string) => void;
  sourceOptions: FilterOption[];
  analyticsLoading: boolean;
  analyticsError: string | null;
  analyticsRows: Array<{
    handle: string;
    follower_count?: number;
    following_count?: number;
    post_count?: number;
    source_key?: string;
  }>;
  localTags: Record<string, string[]>;
  tagFilter: string;
  onTagFilterChange: (value: string) => void;
  analyticsBucket: string | null;
  onAnalyticsBucketChange: (value: string | null) => void;
  discoveredAccounts: DiscoveredAccount[];
  onSelectAccount: (account: DiscoveredAccount) => void;
}) {
  const {
    analyticsMetric,
    onAnalyticsMetricChange,
    sourceFilterKey,
    onSourceFilterKeyChange,
    sourceOptions,
    analyticsLoading,
    analyticsError,
    analyticsRows,
    localTags,
    tagFilter,
    onTagFilterChange,
    analyticsBucket,
    onAnalyticsBucketChange,
    discoveredAccounts,
    onSelectAccount,
  } = props;

  return (
    <div className="flex-1 overflow-y-auto space-y-3">
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-1">Analytics</div>
        <div className="text-xs text-gray-500 dark:text-gray-400 mb-3">
          Uses latest snapshot per target.
        </div>

        <div className="flex items-center gap-2 mb-4">
          <select
            value={analyticsMetric}
            onChange={(e) => onAnalyticsMetricChange(e.target.value as AnalyticsMetric)}
            className="px-2 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
          >
            <option value="followers">Followers</option>
            <option value="following">Following</option>
            <option value="posts">Posts</option>
          </select>

          <select
            value={sourceFilterKey}
            onChange={(e) => onSourceFilterKeyChange(e.target.value)}
            className="px-2 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600 max-w-[240px]"
            title="Filter by source"
          >
            <option value="all">All sources</option>
            {sourceOptions.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label} ({s.count})
              </option>
            ))}
          </select>
        </div>

        {analyticsError && (
          <div className="text-xs text-red-600 dark:text-red-400 mb-2">{analyticsError}</div>
        )}

        {analyticsLoading ? (
          <div className="text-sm text-gray-500 dark:text-gray-400">Loading...</div>
        ) : (() => {
          const allTags = Array.from(new Set(
            (Object.entries(localTags) as Array<[string, string[]]>).flatMap(([, tags]) =>
              tags.map((t) => t.trim()).filter((t) => t)
            )
          )).sort((a, b) => a.localeCompare(b));

          const rows = analyticsRows.filter((r) => {
            if (sourceFilterKey !== 'all' && r.source_key !== sourceFilterKey) return false;
            if (tagFilter === 'all') return true;
            const tags = localTags[r.handle] || [];
            return tags.includes(tagFilter);
          });
          const values = rows
            .map((r) => analyticsMetric === 'followers' ? r.follower_count : analyticsMetric === 'following' ? r.following_count : r.post_count)
            .filter((v): v is number => typeof v === 'number' && Number.isFinite(v));

          const buckets = [
            { label: '0-1K', min: 0, max: 1_000 },
            { label: '1K-10K', min: 1_000, max: 10_000 },
            { label: '10K-100K', min: 10_000, max: 100_000 },
            { label: '100K-1M', min: 100_000, max: 1_000_000 },
            { label: '1M+', min: 1_000_000, max: Infinity },
          ];

          const counts = buckets.map((b) => ({
            ...b,
            count: values.filter((v) => v >= b.min && v < b.max).length,
          }));
          const maxCount = Math.max(1, ...counts.map((c) => c.count));

          return (
            <div className="space-y-2">
              <div className="text-xs text-gray-500 dark:text-gray-400">
                Targets with snapshots: {rows.length} (numeric: {values.length})
              </div>
              <div className="flex items-center gap-2 mb-2">
                <select
                  value={tagFilter}
                  onChange={(e) => onTagFilterChange(e.target.value)}
                  className="px-2 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
                >
                  <option value="all">All tags</option>
                  {allTags.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
                {analyticsBucket && (
                  <button
                    onClick={() => onAnalyticsBucketChange(null)}
                    className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                  >
                    Clear segment
                  </button>
                )}
              </div>
              {counts.map((c) => (
                <button
                  key={c.label}
                  onClick={() => onAnalyticsBucketChange(c.label)}
                  className={`w-full flex items-center gap-3 ${analyticsBucket === c.label ? 'opacity-100' : ''}`}
                >
                  <div className="w-20 text-xs text-gray-600 dark:text-gray-300">{c.label}</div>
                  <div className="flex-1 h-2 bg-gray-100 dark:bg-gray-700 rounded">
                    <div
                      className="h-2 bg-blue-600 rounded"
                      style={{ width: `${(c.count / maxCount) * 100}%` }}
                    />
                  </div>
                  <div className="w-10 text-right text-xs text-gray-600 dark:text-gray-300">{c.count}</div>
                </button>
              ))}

              {analyticsBucket && (() => {
                const bucketDef = buckets.find((b) => b.label === analyticsBucket);
                if (!bucketDef) return null;
                const inBucket = rows
                  .map((r) => {
                    const v = analyticsMetric === 'followers' ? r.follower_count : analyticsMetric === 'following' ? r.following_count : r.post_count;
                    return { ...r, value: v };
                  })
                  .filter((r) => typeof r.value === 'number' && (r.value as number) >= bucketDef.min && (r.value as number) < bucketDef.max)
                  .sort((a, b) => (b.value as number) - (a.value as number))
                  .slice(0, 30);
                return (
                  <div className="mt-3">
                    <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                      Segment: {analyticsBucket} (top {inBucket.length})
                    </div>
                    <div className="space-y-1">
                      {inBucket.map((r) => (
                        <button
                          key={r.handle}
                          onClick={() => {
                            const acc = discoveredAccounts.find((a) => a.handle === r.handle);
                            if (acc) {
                              onSelectAccount(acc);
                            }
                          }}
                          className="w-full flex items-center justify-between text-xs p-2 bg-gray-50 dark:bg-gray-900/30 rounded border border-gray-200 dark:border-gray-700 hover:border-blue-500 dark:hover:border-blue-500"
                        >
                          <span className="text-gray-900 dark:text-gray-100">@{r.handle}</span>
                          <span className="text-gray-500 dark:text-gray-400">{typeof r.value === 'number' ? formatCount(r.value) : '—'}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })()}
            </div>
          );
        })()}
      </div>
    </div>
  );
}

