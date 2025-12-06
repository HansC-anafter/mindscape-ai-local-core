'use client';

import React from 'react';
import { DataSourceWithOverlay } from '@/hooks/useDataSourceOverlay';

interface DataSourceBindingCardProps {
  dataSource: DataSourceWithOverlay;
  onEdit: () => void;
  onDelete: () => void;
}

export default function DataSourceBindingCard({
  dataSource,
  onEdit,
  onDelete,
}: DataSourceBindingCardProps) {
  const getAccessModeLabel = (mode: string) => {
    switch (mode) {
      case 'read':
        return 'Read';
      case 'write':
        return 'Write';
      case 'admin':
        return 'Admin';
      default:
        return mode;
    }
  };

  const getAccessModeColor = (mode: string) => {
    switch (mode) {
      case 'read':
        return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300';
      case 'write':
        return 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300';
      case 'admin':
        return 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300';
      default:
        return 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300';
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
              {dataSource.display_name || dataSource.data_source_name}
            </span>
            {dataSource.overlay_applied && (
              <span className="text-xs px-2 py-1 bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300 rounded">
                Overlay
              </span>
            )}
          </div>
          <div className="space-y-1 text-sm text-gray-600 dark:text-gray-400">
            <div className="flex items-center gap-2">
              <span>Type:</span>
              <span className="font-medium">{dataSource.data_source_type}</span>
            </div>
            <div className="flex items-center gap-2">
              <span>ID:</span>
              <span className="font-mono text-xs">{dataSource.data_source_id}</span>
            </div>
            <div className="flex items-center gap-2">
              <span>Access:</span>
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${getAccessModeColor(dataSource.effective_access_mode)}`}>
                {getAccessModeLabel(dataSource.effective_access_mode)}
              </span>
              {dataSource.original_access_mode !== dataSource.effective_access_mode && (
                <span className="text-xs text-gray-500">
                  (was {getAccessModeLabel(dataSource.original_access_mode)})
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span>Status:</span>
              <span className={dataSource.enabled ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}>
                {dataSource.enabled ? 'Enabled' : 'Disabled'}
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 ml-4">
          <button
            onClick={onEdit}
            className="px-3 py-1.5 text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-medium"
          >
            Edit
          </button>
          <button
            onClick={onDelete}
            className="px-3 py-1.5 text-sm text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 font-medium"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

