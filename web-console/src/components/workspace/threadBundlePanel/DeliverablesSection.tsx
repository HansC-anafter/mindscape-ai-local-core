import React from 'react';

import type { ThreadBundle } from '@/hooks/useThreadBundle';
import { formatLocalDateTime } from '@/lib/time';

export function DeliverablesSection({ items }: { items: ThreadBundle['deliverables'] }) {
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <h3 className="text-lg font-medium mb-2">No Deliverables</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Outputs from completed playbooks will appear here.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div
          key={item.id}
          className="p-3 border dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <h4 className="font-medium text-gray-900 dark:text-gray-100">{item.title}</h4>
              <div className="mt-1 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                <span>{item.artifact_type}</span>
                <span>-</span>
                <span>{item.source}</span>
                <span>-</span>
                <span>{item.status}</span>
              </div>
            </div>
          </div>
          <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
            Updated {formatLocalDateTime(item.updated_at)}
          </div>
        </div>
      ))}
    </div>
  );
}
