import React from 'react';

import type { ThreadBundle } from '@/hooks/useThreadBundle';

export function SourcesSection({ items }: { items: ThreadBundle['sources'] }) {
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <h3 className="text-lg font-medium mb-2">No Sources</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Sources and connectors will appear here.
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
              <h4 className="font-medium text-gray-900 dark:text-gray-100">{item.display_name}</h4>
              <div className="mt-1 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                <span>{item.type}</span>
                <span>-</span>
                <span>{item.sync_status}</span>
                {item.permissions.length > 0 && (
                  <>
                    <span>-</span>
                    <span>{item.permissions.join(', ')}</span>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
