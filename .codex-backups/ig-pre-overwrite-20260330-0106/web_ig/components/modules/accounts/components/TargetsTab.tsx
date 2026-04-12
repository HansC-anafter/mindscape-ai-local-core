import React from 'react';

import type { DiscoveredAccount } from '../types';
import { TargetsGrid } from './TargetsGrid';
import { TargetsList } from './TargetsList';

export function TargetsTab(props: {
  loading: boolean;
  error?: string | null;
  filteredTargets: DiscoveredAccount[];
  searchQuery: string;
  targetsViewMode: 'grid' | 'list';
  apiUrl: string;
  getTagsForHandle: (handle: string, fallbackTags?: string[]) => string[];
  onSelect: (account: DiscoveredAccount) => void;
  onRetry?: () => void;
  loadMore?: () => void;
  hasMore?: boolean;
  loadingMore?: boolean;
}) {
  const {
    loading,
    error,
    filteredTargets,
    searchQuery,
    targetsViewMode,
    apiUrl,
    getTagsForHandle,
    onSelect,
    onRetry,
    loadMore,
    hasMore,
    loadingMore,
  } = props;

  return (
    <div className="flex-1 min-h-0 overflow-hidden">
      {loading && filteredTargets.length === 0 ? (
        <div className="text-center py-6 text-sm text-gray-500 dark:text-gray-400">
          Loading targets...
        </div>
      ) : error && filteredTargets.length === 0 ? (
        <div className="text-center py-6 text-sm text-red-600 dark:text-red-400">
          <div>{error}</div>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-3 inline-flex items-center rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800"
            >
              Retry
            </button>
          )}
        </div>
      ) : filteredTargets.length === 0 ? (
        <div className="text-center py-6 text-sm text-gray-500 dark:text-gray-400">
          {searchQuery ? 'No matching targets found' : 'No targets yet. Run a capture first.'}
        </div>
      ) : targetsViewMode === 'grid' ? (
        <TargetsGrid
          apiUrl={apiUrl}
          targets={filteredTargets}
          getTagsForHandle={getTagsForHandle}
          onSelect={onSelect}
          loadMore={loadMore}
          hasMore={hasMore}
          loadingMore={loadingMore}
        />
      ) : (
        <TargetsList
          apiUrl={apiUrl}
          targets={filteredTargets}
          onSelect={onSelect}
          loadMore={loadMore}
          hasMore={hasMore}
          loadingMore={loadingMore}
        />
      )}
    </div>
  );
}
