import React from 'react';

import type { FilterOption } from '../selectors';

export function KnownSourcesCard(props: {
  sourceOptions: FilterOption[];
  onViewAllTargets: () => void;
  onSelectSourceKey: (key: string) => void;
}) {
  const { sourceOptions, onViewAllTargets, onSelectSourceKey } = props;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Known sources</h3>
        <button
          onClick={onViewAllTargets}
          className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
        >
          View all targets
        </button>
      </div>
      {sourceOptions.length === 0 ? (
        <div className="text-sm text-gray-500 dark:text-gray-400">
          No sources found yet. Run a capture first.
        </div>
      ) : (
        <div className="space-y-2">
          {sourceOptions.map((s) => (
            <button
              key={s.key}
              onClick={() => onSelectSourceKey(s.key)}
              className="w-full text-left p-3 bg-gray-50 dark:bg-gray-900/30 rounded border border-gray-200 dark:border-gray-700 hover:border-blue-500 dark:hover:border-blue-500 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">{s.label}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">{s.count} targets</div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

