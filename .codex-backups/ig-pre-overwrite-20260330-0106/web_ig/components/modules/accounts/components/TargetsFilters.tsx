import React from 'react';
import { Search, X } from 'lucide-react';

import type { FilterOption } from '../selectors';

export function TargetsFilters(props: {
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
  sourceFilterKey: string;
  onSourceFilterKeyChange: (value: string) => void;
  seedFilterKey: string;
  onSeedFilterKeyChange: (value: string) => void;
  sourceOptions: FilterOption[];
  seedOptions: FilterOption[];
}) {
  const {
    searchQuery,
    onSearchQueryChange,
    sourceFilterKey,
    onSourceFilterKeyChange,
    seedFilterKey,
    onSeedFilterKeyChange,
    sourceOptions,
    seedOptions,
  } = props;

  return (
    <div className="mb-4">
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchQueryChange(e.target.value)}
            placeholder="Search targets..."
            className="w-full pl-10 pr-9 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => onSearchQueryChange('')}
              className="absolute right-2.5 top-1/2 transform -translate-y-1/2 p-0.5 rounded-full text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors"
              title="Clear search"
              aria-label="Clear search"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
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
        <select
          value={seedFilterKey}
          onChange={(e) => onSeedFilterKeyChange(e.target.value)}
          className="px-2 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600 max-w-[240px]"
          title="Filter by seed"
        >
          <option value="all">All seeds</option>
          {seedOptions.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label} ({s.count})
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

