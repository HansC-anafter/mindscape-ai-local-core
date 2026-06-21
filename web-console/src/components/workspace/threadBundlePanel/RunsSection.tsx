'use client';

import React, { useState } from 'react';

import type { ThreadBundle } from '@/hooks/useThreadBundle';
import { formatLocalDateTime } from '@/lib/time';

import { cn } from './sectionConfig';

export function RunsSection({ items }: { items: ThreadBundle['runs'] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <h3 className="text-lg font-medium mb-2">No Runs</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Playbook run records will appear here.
        </p>
      </div>
    );
  }

  const statusConfig: Record<string, { color: string; label: string }> = {
    completed: { color: 'text-green-600 dark:text-green-400', label: 'Completed' },
    running: { color: 'text-blue-600 dark:text-blue-400', label: 'Running' },
    failed: { color: 'text-red-600 dark:text-red-400', label: 'Failed' },
    cancelled: { color: 'text-gray-500 dark:text-gray-400', label: 'Cancelled' },
  };

  return (
    <div className="space-y-3">
      {items.map((item) => {
        const status = statusConfig[item.status] || statusConfig.running;
        const isExpanded = expandedId === item.id;
        const hasDetails = Boolean(item.result_summary);

        return (
          <div
            key={item.id}
            className={cn(
              'p-3 border dark:border-gray-700 rounded-lg transition-colors',
              hasDetails ? 'cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800' : '',
            )}
            onClick={() => hasDetails && setExpandedId(isExpanded ? null : item.id)}
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h4 className="font-medium text-gray-900 dark:text-gray-100">{item.playbook_name}</h4>
                </div>
                <div className="mt-1 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                  <span className={status.color}>{status.label}</span>
                  <span>-</span>
                  <span>{item.steps_completed}/{item.steps_total} steps</span>
                  {item.duration_ms && (
                    <>
                      <span>-</span>
                      <span>{(item.duration_ms / 1000).toFixed(1)}s</span>
                    </>
                  )}
                </div>
              </div>
              {hasDetails && (
                <span className="text-xs text-gray-400 mt-1">{isExpanded ? 'Collapse' : 'Expand'}</span>
              )}
            </div>
            <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
              Started {formatLocalDateTime(item.started_at)}
            </div>
            {isExpanded && item.result_summary && (
              <div className="mt-3 pt-3 border-t dark:border-gray-700">
                <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                  {item.result_summary}
                </p>
                {item.storage_ref && (
                  <div className="mt-2 text-xs text-blue-500 dark:text-blue-400">
                    {item.storage_ref}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
