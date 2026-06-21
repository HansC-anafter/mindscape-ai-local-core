import React from 'react';

import type { ThreadBundle } from '@/hooks/useThreadBundle';

export function OverviewSection({ bundle }: { bundle: ThreadBundle }) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">Status</h3>
        <div className="text-base font-medium">
          {bundle.overview.status === 'in_progress' && 'In Progress'}
          {bundle.overview.status === 'delivered' && 'Delivered'}
          {bundle.overview.status === 'pending_data' && 'Waiting for Data'}
        </div>
      </div>

      {bundle.overview.summary && (
        <div>
          <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">Summary</h3>
          <p className="text-sm text-gray-700 dark:text-gray-300">{bundle.overview.summary}</p>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 pt-4 border-t dark:border-gray-700">
        <div>
          <div className="text-sm text-gray-500 dark:text-gray-400">Deliverables</div>
          <div className="text-lg font-semibold">{bundle.deliverables.length}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500 dark:text-gray-400">References</div>
          <div className="text-lg font-semibold">{bundle.references.length}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500 dark:text-gray-400">Runs</div>
          <div className="text-lg font-semibold">{bundle.runs.length}</div>
        </div>
        <div>
          <div className="text-sm text-gray-500 dark:text-gray-400">Sources</div>
          <div className="text-lg font-semibold">{bundle.sources.length}</div>
        </div>
      </div>
    </div>
  );
}
