'use client';

import React, { useState } from 'react';
import { t } from '@/lib/i18n';

export interface ConflictInfo {
  instance_type: string;
  instance_id: string;
  local_version: number;
  cloud_version: number;
  local_data?: any;
  cloud_data?: any;
  resolution_options: string[];
}

interface ConflictResolverProps {
  conflict: ConflictInfo;
  onResolve: (resolution: 'use_local' | 'use_cloud' | 'manual_merge', mergedData?: any) => void;
  onCancel: () => void;
}

export default function ConflictResolver({ conflict, onResolve, onCancel }: ConflictResolverProps) {
  const [selectedResolution, setSelectedResolution] = useState<string>('');
  const [showDiff, setShowDiff] = useState(false);

  const handleResolve = () => {
    if (selectedResolution === 'manual_merge') {
      onResolve('manual_merge', conflict.local_data);
    } else {
      onResolve(selectedResolution as 'use_local' | 'use_cloud');
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-4xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        <div className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {t('conflictResolution' as any)}
            </h2>
            <button
              onClick={onCancel}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            </button>
          </div>

          <div className="mb-4">
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
              {t('conflictDetected' as any)}: {conflict.instance_type}/{conflict.instance_id}
            </p>
            <div className="flex items-center gap-4 text-sm">
              <div>
                <span className="text-gray-600 dark:text-gray-400">{t('localVersion' as any)}:</span>
                <span className="ml-2 font-medium">{conflict.local_version}</span>
              </div>
              <div>
                <span className="text-gray-600 dark:text-gray-400">{t('cloudVersion' as any)}:</span>
                <span className="ml-2 font-medium">{conflict.cloud_version}</span>
              </div>
            </div>
          </div>

          <div className="mb-4">
            <button
              onClick={() => setShowDiff(!showDiff)}
              className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
            >
              {showDiff ? t('hideDiff' as any) : t('showDiff' as any)}
            </button>
            {showDiff && (
              <div className="mt-2 grid grid-cols-2 gap-4">
                <div className="border rounded p-3">
                  <h4 className="font-medium mb-2 text-sm">{t('localData' as any)}</h4>
                  <pre className="text-xs overflow-auto max-h-64 bg-gray-50 dark:bg-gray-900 p-2 rounded">
                    {JSON.stringify(conflict.local_data, null, 2)}
                  </pre>
                </div>
                <div className="border rounded p-3">
                  <h4 className="font-medium mb-2 text-sm">{t('cloudData' as any)}</h4>
                  <pre className="text-xs overflow-auto max-h-64 bg-gray-50 dark:bg-gray-900 p-2 rounded">
                    {JSON.stringify(conflict.cloud_data, null, 2)}
                  </pre>
                </div>
              </div>
            )}
          </div>

          <div className="mb-4">
            <h3 className="text-sm font-medium mb-2">{t('selectResolution' as any)}</h3>
            <div className="space-y-2">
              {conflict.resolution_options.includes('use_local') && (
                <label className="flex items-center p-3 border rounded cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700">
                  <input
                    type="radio"
                    name="resolution"
                    value="use_local"
                    checked={selectedResolution === 'use_local'}
                    onChange={(e) => setSelectedResolution(e.target.value)}
                    className="mr-3"
                  />
                  <div>
                    <div className="font-medium text-sm">{t('useLocal' as any)}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">{t('useLocalDescription' as any)}</div>
                  </div>
                </label>
              )}
              {conflict.resolution_options.includes('use_cloud') && (
                <label className="flex items-center p-3 border rounded cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700">
                  <input
                    type="radio"
                    name="resolution"
                    value="use_cloud"
                    checked={selectedResolution === 'use_cloud'}
                    onChange={(e) => setSelectedResolution(e.target.value)}
                    className="mr-3"
                  />
                  <div>
                    <div className="font-medium text-sm">{t('useCloud' as any)}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">{t('useCloudDescription' as any)}</div>
                  </div>
                </label>
              )}
              {conflict.resolution_options.includes('manual_merge') && (
                <label className="flex items-center p-3 border rounded cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700">
                  <input
                    type="radio"
                    name="resolution"
                    value="manual_merge"
                    checked={selectedResolution === 'manual_merge'}
                    onChange={(e) => setSelectedResolution(e.target.value)}
                    className="mr-3"
                  />
                  <div>
                    <div className="font-medium text-sm">{t('manualMerge' as any)}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">{t('manualMergeDescription' as any)}</div>
                  </div>
                </label>
              )}
            </div>
          </div>

          <div className="flex justify-end gap-2">
            <button
              onClick={onCancel}
              className="px-4 py-2 text-sm border rounded hover:bg-gray-50 dark:hover:bg-gray-700"
            >
              {t('cancel' as any)}
            </button>
            <button
              onClick={handleResolve}
              disabled={!selectedResolution}
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {t('resolve' as any)}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

