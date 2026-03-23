'use client';

import React, { useMemo, useState } from 'react';

import { useT } from '@/lib/i18n';

import {
  formatTimelineItemTime,
  getSortedNonExecutionTimelineItems,
} from './helpers';
import type { TimelineItem } from './types';

interface TimelineItemsDrawerProps {
  timelineItems: TimelineItem[];
}

export default function TimelineItemsDrawer({
  timelineItems,
}: TimelineItemsDrawerProps) {
  const t = useT();
  const [isCollapsed, setIsCollapsed] = useState(true);
  const nonExecutionItems = useMemo(
    () => getSortedNonExecutionTimelineItems(timelineItems),
    [timelineItems]
  );

  if (nonExecutionItems.length === 0) {
    return null;
  }

  return (
    <div className="flex-shrink-0 border-t dark:border-gray-700">
      <div
        className="flex cursor-pointer items-center justify-between px-3 py-2 transition-colors hover:bg-surface-secondary dark:hover:bg-gray-800"
        onClick={() => setIsCollapsed((previous) => !previous)}
      >
        <div className="flex items-center gap-2">
          <span className="text-xs text-secondary">{isCollapsed ? '▶' : '▼'}</span>
          <span className="text-xs font-semibold text-primary dark:text-gray-300">
            {t('timelineItems' as any) || 'Timeline Items'}
          </span>
          <span className="text-[10px] text-tertiary">({nonExecutionItems.length})</span>
        </div>
      </div>

      <div
        className={`overflow-hidden transition-all duration-300 ease-in-out ${
          isCollapsed ? 'max-h-0 opacity-0' : 'max-h-[300px] opacity-100'
        }`}
      >
        {!isCollapsed ? (
          <div className="max-h-[300px] overflow-y-auto px-3 pb-2">
            <div className="space-y-1.5">
              {nonExecutionItems.map((item) => (
                <div
                  key={item.id}
                  className="w-full rounded border border-default bg-surface-accent p-2 text-left transition-all hover:border-default hover:shadow-sm dark:border-gray-700 dark:bg-gray-800 dark:hover:border-gray-600"
                >
                  <div className="mb-1 flex items-center justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-xs font-medium text-primary dark:text-gray-100">
                        {item.title || 'Untitled'}
                      </div>
                      {item.summary ? (
                        <div className="mt-0.5 line-clamp-2 text-[10px] text-secondary dark:text-gray-300">
                          {item.summary}
                        </div>
                      ) : null}
                      <div className="mt-0.5 text-[10px] text-tertiary dark:text-gray-300">
                        {item.type || 'PLAN'}
                      </div>
                    </div>
                    <span className="ml-2 text-[10px] text-tertiary dark:text-gray-300">
                      {formatTimelineItemTime(item.created_at)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
