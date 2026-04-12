import React from 'react';

export function CaptureFollowingListCard(props: {
  onOpenFollowingAnalyzer: () => void;
  onRefreshTargets: () => void;
}) {
  const { onOpenFollowingAnalyzer, onRefreshTargets } = props;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <div className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-1">Capture following list</div>
      <div className="text-xs text-gray-500 dark:text-gray-400">
        Creates a following-list asset and updates Targets.
      </div>
      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={onOpenFollowingAnalyzer}
          className="px-3 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Open Following Analyzer
        </button>
        <button
          onClick={onRefreshTargets}
          className="px-3 py-2 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded hover:bg-gray-200 dark:hover:bg-gray-600"
        >
          Refresh Targets
        </button>
      </div>
    </div>
  );
}

