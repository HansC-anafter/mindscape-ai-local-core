import React from 'react';

import { t } from '../../../../../lib/i18n';

interface LineConnectionModeSectionProps {
  connectionMode: 'local' | 'remote';
  onConnectionModeChange: (mode: 'local' | 'remote') => void;
}

export function LineConnectionModeSection({
  connectionMode,
  onConnectionModeChange,
}: LineConnectionModeSectionProps) {
  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-4">
        {t('lineConnectionMode' as any)}
      </h3>
      <div className="space-y-3">
        <label className="flex items-start gap-3 p-3 border border-gray-200 dark:border-gray-700 rounded-md cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50">
          <input
            type="radio"
            name="connectionMode"
            value="local"
            checked={connectionMode === 'local'}
            onChange={(event) => onConnectionModeChange(event.target.value as 'local' | 'remote')}
            className="mt-1"
          />
          <div className="flex-1">
            <div className="font-medium text-gray-900 dark:text-gray-100">
              {t('lineDirectConnection' as any)}
            </div>
            <div className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {t('lineDirectConnectionDescription' as any)}
            </div>
          </div>
        </label>
        <label className="flex items-start gap-3 p-3 border border-gray-200 dark:border-gray-700 rounded-md cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50">
          <input
            type="radio"
            name="connectionMode"
            value="remote"
            checked={connectionMode === 'remote'}
            onChange={(event) => onConnectionModeChange(event.target.value as 'local' | 'remote')}
            className="mt-1"
          />
          <div className="flex-1">
            <div className="font-medium text-gray-900 dark:text-gray-100">
              {t('lineCloudRemoteTools' as any)}
            </div>
            <div className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {t('lineCloudRemoteToolsDescription' as any)}
            </div>
          </div>
        </label>
      </div>
    </div>
  );
}
