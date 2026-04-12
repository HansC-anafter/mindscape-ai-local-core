import React from 'react';
import { Grid3x3, Layout, List } from 'lucide-react';

import type { PostStatus } from '../../types';
import type { WorkbenchModuleType, WorkbenchViewMode } from '../types';
import { WORKBENCH_MODULES } from '../moduleRegistry';

export function WorkbenchHeader(props: {
  activeModule: WorkbenchModuleType | null;
  onBackToContent: () => void;

  viewMode: WorkbenchViewMode;
  onViewModeChange: (mode: WorkbenchViewMode) => void;

  statusFilter: PostStatus | 'all';
  onStatusFilterChange: (value: PostStatus | 'all') => void;
  statusButtons: Array<{ id: string; label: string; count: number }>;
}) {
  const {
    activeModule,
    onBackToContent,
    viewMode,
    onViewModeChange,
    statusFilter,
    onStatusFilterChange,
    statusButtons,
  } = props;

  return (
    <div className="border-b dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-3">
      {!activeModule ? (
        <>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">Content Pipeline</h1>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => onViewModeChange('grid')}
                className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                  viewMode === 'grid'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                }`}
              >
                <Grid3x3 className="w-4 h-4 inline mr-1" />
                Grid
              </button>
              <button
                onClick={() => onViewModeChange('timeline')}
                className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                  viewMode === 'timeline'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                }`}
              >
                <List className="w-4 h-4 inline mr-1" />
                Timeline
              </button>
              <button
                onClick={() => onViewModeChange('kanban')}
                className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                  viewMode === 'kanban'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                }`}
              >
                <Layout className="w-4 h-4 inline mr-1" />
                Kanban
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {statusButtons.map((status) => (
              <button
                key={status.id}
                onClick={() => onStatusFilterChange(status.id as PostStatus | 'all')}
                className={`px-3 py-1.5 text-xs rounded-lg transition-colors flex items-center gap-2 ${
                  statusFilter === status.id
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                }`}
              >
                <span>{status.label}</span>
                {status.count > 0 && (
                  <span
                    className={`px-1.5 py-0.5 rounded text-xs ${
                      statusFilter === status.id
                        ? 'bg-blue-500 text-white'
                        : 'bg-gray-200 dark:bg-gray-600 text-gray-700 dark:text-gray-300'
                    }`}
                  >
                    {status.count}
                  </span>
                )}
              </button>
            ))}
          </div>
        </>
      ) : (
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
            {WORKBENCH_MODULES.find((m) => m.id === activeModule)?.label || 'Module'}
          </h1>
          <button
            onClick={onBackToContent}
            className="px-3 py-1.5 text-sm rounded-lg bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600"
            title="Back to Content"
          >
            Back to Content
          </button>
        </div>
      )}
    </div>
  );
}

