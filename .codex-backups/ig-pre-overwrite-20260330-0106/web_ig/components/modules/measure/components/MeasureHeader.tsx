import React from 'react';
import { Target } from 'lucide-react';

export function MeasureHeader(props: {
  postSummaryText: string;
  onOpenBackfill: () => void;
}) {
  const { postSummaryText, onOpenBackfill } = props;

  return (
    <div className="mb-4">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
          Metrics Backfill
        </h2>
        <button
          onClick={onOpenBackfill}
          className="px-3 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 flex items-center gap-2"
        >
          <Target className="w-3.5 h-3.5" />
          Manual Backfill
        </button>
      </div>
      <p className="text-xs text-gray-500 dark:text-gray-400">
        {postSummaryText}
      </p>
    </div>
  );
}

