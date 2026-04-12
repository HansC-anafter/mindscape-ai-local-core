import React from 'react';

import type { Metrics } from '../types';

export function BackfillDialog(props: {
  open: boolean;
  loading: boolean;
  metrics: Partial<Metrics>;
  onMetricsChange: (next: Partial<Metrics>) => void;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { open, loading, metrics, onMetricsChange, onConfirm, onCancel } = props;

  if (!open) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 max-w-md w-full mx-4">
        <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">
          Manual Metrics Backfill
        </h3>
        <div className="space-y-3">
          <div>
            <label className="text-sm text-gray-700 dark:text-gray-300 mb-1 block">
              Likes
            </label>
            <input
              type="number"
              value={metrics.likes || ''}
              onChange={(e) => onMetricsChange({ ...metrics, likes: parseInt(e.target.value, 10) || undefined })}
              className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
              placeholder="Optional"
            />
          </div>
          <div>
            <label className="text-sm text-gray-700 dark:text-gray-300 mb-1 block">
              Comments
            </label>
            <input
              type="number"
              value={metrics.comments || ''}
              onChange={(e) => onMetricsChange({ ...metrics, comments: parseInt(e.target.value, 10) || undefined })}
              className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
              placeholder="Optional"
            />
          </div>
          <div>
            <label className="text-sm text-gray-700 dark:text-gray-300 mb-1 block">
              Shares
            </label>
            <input
              type="number"
              value={metrics.shares || ''}
              onChange={(e) => onMetricsChange({ ...metrics, shares: parseInt(e.target.value, 10) || undefined })}
              className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
              placeholder="Optional"
            />
          </div>
          <div>
            <label className="text-sm text-gray-700 dark:text-gray-300 mb-1 block">
              Saves
            </label>
            <input
              type="number"
              value={metrics.saves || ''}
              onChange={(e) => onMetricsChange({ ...metrics, saves: parseInt(e.target.value, 10) || undefined })}
              className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
              placeholder="Optional"
            />
          </div>
          <div>
            <label className="text-sm text-gray-700 dark:text-gray-300 mb-1 block">
              Reach
            </label>
            <input
              type="number"
              value={metrics.reach || ''}
              onChange={(e) => onMetricsChange({ ...metrics, reach: parseInt(e.target.value, 10) || undefined })}
              className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
              placeholder="Optional"
            />
          </div>
          <div>
            <label className="text-sm text-gray-700 dark:text-gray-300 mb-1 block">
              Impressions
            </label>
            <input
              type="number"
              value={metrics.impressions || ''}
              onChange={(e) => onMetricsChange({ ...metrics, impressions: parseInt(e.target.value, 10) || undefined })}
              className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600"
              placeholder="Optional"
            />
          </div>
          <div className="flex items-center gap-2 mt-4">
            <button
              onClick={onConfirm}
              disabled={loading}
              className="flex-1 px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              Confirm Backfill
            </button>
            <button
              onClick={onCancel}
              className="flex-1 px-4 py-2 text-sm bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-300 dark:hover:bg-gray-600"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

