import React from 'react';

import type { Metrics } from '../types';

export function MetricsCards(props: { metrics: Metrics | null }) {
  const { metrics } = props;

  if (!metrics) {
    return (
      <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
        <p className="text-sm text-yellow-800 dark:text-yellow-300">
          No metrics data. Please backfill first.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">
        Metrics Data
      </h3>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {metrics.likes !== undefined && (
          <div className="p-3 bg-gray-50 dark:bg-gray-700 rounded">
            <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Likes</div>
            <div className="text-lg font-bold text-gray-900 dark:text-gray-100">
              {metrics.likes.toLocaleString()}
            </div>
          </div>
        )}
        {metrics.comments !== undefined && (
          <div className="p-3 bg-gray-50 dark:bg-gray-700 rounded">
            <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Comments</div>
            <div className="text-lg font-bold text-gray-900 dark:text-gray-100">
              {metrics.comments.toLocaleString()}
            </div>
          </div>
        )}
        {metrics.shares !== undefined && (
          <div className="p-3 bg-gray-50 dark:bg-gray-700 rounded">
            <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Shares</div>
            <div className="text-lg font-bold text-gray-900 dark:text-gray-100">
              {metrics.shares.toLocaleString()}
            </div>
          </div>
        )}
        {metrics.saves !== undefined && (
          <div className="p-3 bg-gray-50 dark:bg-gray-700 rounded">
            <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Saves</div>
            <div className="text-lg font-bold text-gray-900 dark:text-gray-100">
              {metrics.saves.toLocaleString()}
            </div>
          </div>
        )}
        {metrics.reach !== undefined && (
          <div className="p-3 bg-gray-50 dark:bg-gray-700 rounded">
            <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Reach</div>
            <div className="text-lg font-bold text-gray-900 dark:text-gray-100">
              {metrics.reach.toLocaleString()}
            </div>
          </div>
        )}
        {metrics.impressions !== undefined && (
          <div className="p-3 bg-gray-50 dark:bg-gray-700 rounded">
            <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Impressions</div>
            <div className="text-lg font-bold text-gray-900 dark:text-gray-100">
              {metrics.impressions.toLocaleString()}
            </div>
          </div>
        )}
        {metrics.engagement_rate !== undefined && (
          <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded">
            <div className="text-xs text-blue-600 dark:text-blue-400 mb-1">Engagement Rate</div>
            <div className="text-lg font-bold text-blue-900 dark:text-blue-100">
              {(metrics.engagement_rate * 100).toFixed(2)}%
            </div>
          </div>
        )}
      </div>
      {metrics.backfilled_at && (
        <div className="mt-3 text-xs text-gray-500 dark:text-gray-400">
          Backfilled at: {new Date(metrics.backfilled_at).toLocaleString()}
          {metrics.backfill_source && ` (${metrics.backfill_source})`}
        </div>
      )}
    </div>
  );
}

