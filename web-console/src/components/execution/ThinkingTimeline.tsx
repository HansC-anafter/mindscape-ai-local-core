'use client';

import React from 'react';

export interface TimelineEntry {
  id: string;
  timestamp: string; // ISO string or formatted time
  summary: string;
  stepCount?: number;
  artifactCount?: number;
  status?: 'completed' | 'in_progress' | 'error';
}

interface ThinkingTimelineProps {
  entries: TimelineEntry[];
  maxEntries?: number; // Default to 3
  isCollapsed?: boolean;
  onToggle?: () => void;
  onEntryClick?: (entryId: string) => void;
}

function formatTime(timestamp: string): string {
  try {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const minutes = Math.floor(diff / (1000 * 60));

    if (minutes < 1) return '剛剛';
    if (minutes < 60) return `${minutes} 分鐘前`;
    if (hours < 24) return `${hours} 小時前`;

    return date.toLocaleDateString('zh-TW', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return timestamp;
  }
}

function getStatusIndicator(status?: TimelineEntry['status']): React.ReactNode {
  switch (status) {
    case 'completed':
      return <span className="w-2 h-2 bg-green-500 rounded-full" />;
    case 'in_progress':
      return <span className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />;
    case 'error':
      return <span className="w-2 h-2 bg-red-500 rounded-full" />;
    default:
      return <span className="w-2 h-2 bg-gray-300 dark:bg-gray-600 rounded-full" />;
  }
}

const ThinkingTimeline: React.FC<ThinkingTimelineProps> = ({
  entries,
  maxEntries = 3,
  isCollapsed = false,
  onToggle,
  onEntryClick,
}) => {
  const [expanded, setExpanded] = React.useState(false);
  const displayEntries = entries.slice(0, maxEntries);
  const hasMore = entries.length > maxEntries;
  const recentEntry = entries[0];
  const olderEntries = entries.slice(1, maxEntries);

  return (
    <div className="border-b dark:border-gray-700">
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        onClick={onToggle}
      >
        <div className="flex items-center gap-2">
          <span className="text-gray-500 text-xs">{isCollapsed ? '▶' : '▼'}</span>
          <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">
            思維軌跡
          </span>
          {entries.length > 0 && (
            <span className="text-[10px] text-gray-400">
              最近 {entries.length} 次
            </span>
          )}
        </div>
      </div>

      {/* Content */}
      <div
        className={`overflow-hidden transition-all duration-300 ease-in-out ${
          isCollapsed ? 'max-h-0 opacity-0' : 'max-h-[400px] opacity-100'
        }`}
      >
        <div className="px-3 pb-2">
          {displayEntries.length > 0 ? (
            <div className="space-y-2">
              {/* Always show the most recent entry */}
              {recentEntry && (
                <div
                  className={`
                    group p-2 rounded-md border-l-2
                    ${recentEntry.status === 'in_progress'
                      ? 'border-l-blue-500 bg-blue-50/50 dark:bg-blue-900/20'
                      : 'border-l-purple-300 dark:border-l-purple-600 hover:bg-gray-50 dark:hover:bg-gray-800'
                    }
                    ${onEntryClick ? 'cursor-pointer' : ''}
                    transition-colors
                  `}
                  onClick={() => onEntryClick?.(recentEntry.id)}
                >
                  {/* Time & Status */}
                  <div className="flex items-center gap-2 mb-1">
                    {getStatusIndicator(recentEntry.status)}
                    <span className="text-[10px] text-gray-400 dark:text-gray-500">
                      {formatTime(recentEntry.timestamp)}
                    </span>
                  </div>

                  {/* Summary */}
                  <p className="text-xs text-gray-700 dark:text-gray-300 line-clamp-2">
                    {recentEntry.summary}
                  </p>

                  {/* Stats */}
                  {(recentEntry.stepCount || recentEntry.artifactCount) && (
                    <div className="flex items-center gap-3 mt-1 text-[10px] text-gray-400">
                      {recentEntry.stepCount && (
                        <span>{recentEntry.stepCount} 步驟</span>
                      )}
                      {recentEntry.artifactCount && (
                        <span>{recentEntry.artifactCount} 產出</span>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Show older entries only when expanded */}
              {expanded && olderEntries.length > 0 && (
                <div className="space-y-2 pt-2 border-t dark:border-gray-700">
                  {olderEntries.map((entry) => (
                    <div
                      key={entry.id}
                      className={`
                        group p-2 rounded-md border-l-2
                        ${entry.status === 'in_progress'
                          ? 'border-l-blue-500 bg-blue-50/50 dark:bg-blue-900/20'
                          : 'border-l-purple-300 dark:border-l-purple-600 hover:bg-gray-50 dark:hover:bg-gray-800'
                        }
                        ${onEntryClick ? 'cursor-pointer' : ''}
                        transition-colors
                      `}
                      onClick={() => onEntryClick?.(entry.id)}
                    >
                      {/* Time & Status */}
                      <div className="flex items-center gap-2 mb-1">
                        {getStatusIndicator(entry.status)}
                        <span className="text-[10px] text-gray-400 dark:text-gray-500">
                          {formatTime(entry.timestamp)}
                        </span>
                      </div>

                      {/* Summary */}
                      <p className="text-xs text-gray-700 dark:text-gray-300 line-clamp-2">
                        {entry.summary}
                      </p>

                      {/* Stats */}
                      {(entry.stepCount || entry.artifactCount) && (
                        <div className="flex items-center gap-3 mt-1 text-[10px] text-gray-400">
                          {entry.stepCount && (
                            <span>{entry.stepCount} 步驟</span>
                          )}
                          {entry.artifactCount && (
                            <span>{entry.artifactCount} 產出</span>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Toggle button for older entries */}
              {olderEntries.length > 0 && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setExpanded(!expanded);
                  }}
                  className="w-full text-center text-[10px] text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 py-1 transition-colors"
                >
                  {expanded ? '收起' : `查看更多 (${olderEntries.length}) →`}
                </button>
              )}
            </div>
          ) : (
            <p className="text-xs text-gray-400 dark:text-gray-500 italic py-2">
              尚無執行記錄
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default ThinkingTimeline;

