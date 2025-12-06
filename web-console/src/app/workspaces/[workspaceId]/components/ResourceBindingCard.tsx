'use client';

import React from 'react';
import { WorkspaceResourceBinding } from '@/hooks/useResourceBindings';
import { t } from '@/lib/i18n';

interface ResourceBindingCardProps {
  binding: WorkspaceResourceBinding;
  onEdit: () => void;
  onDelete: () => void;
}

export default function ResourceBindingCard({
  binding,
  onEdit,
  onDelete,
}: ResourceBindingCardProps) {
  const getResourceTypeLabel = (type: string) => {
    switch (type) {
      case 'playbook':
        return 'Playbook';
      case 'tool':
        return 'Tool';
      case 'data_source':
        return 'Data Source';
      default:
        return type;
    }
  };

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

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
              {getResourceTypeLabel(binding.resource_type)}
            </span>
            <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
              {binding.resource_id}
            </span>
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
            <span>Access:</span>
            <span className="font-medium">{getAccessModeLabel(binding.access_mode)}</span>
          </div>
          {Object.keys(binding.overrides || {}).length > 0 && (
            <div className="mt-2 text-xs text-gray-500 dark:text-gray-500">
              Overrides: {Object.keys(binding.overrides || {}).join(', ')}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 ml-4">
          <button
            onClick={onEdit}
            className="px-3 py-1.5 text-sm text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-medium"
          >
            {t('editBinding')}
          </button>
          <button
            onClick={onDelete}
            className="px-3 py-1.5 text-sm text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 font-medium"
          >
            {t('deleteBinding')}
          </button>
        </div>
      </div>
    </div>
  );
}

