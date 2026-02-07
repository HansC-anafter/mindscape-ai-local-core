'use client';

import React, { useState } from 'react';
import { usePlaybookFork } from '@/hooks/usePlaybookFork';
import { useRouter } from 'next/navigation';
import { t } from '@/lib/i18n';

interface ForkPlaybookButtonProps {
  playbookCode: string;
  playbookName: string;
  workspaceId?: string;
  onForkSuccess?: (playbookCode: string) => void;
}

export default function ForkPlaybookButton({
  playbookCode,
  playbookName,
  workspaceId,
  onForkSuccess,
}: ForkPlaybookButtonProps) {
  const { forking, error, forkPlaybook } = usePlaybookFork();
  const router = useRouter();
  const [showForkDialog, setShowForkDialog] = useState(false);
  const [targetWorkspaceId, setTargetWorkspaceId] = useState(workspaceId || '');

  const handleFork = async () => {
    if (!targetWorkspaceId) {
      alert('Please select a workspace');
      return;
    }

    try {
      const result = await forkPlaybook(playbookCode, {
        target_workspace_id: targetWorkspaceId,
      });

      setShowForkDialog(false);

      if (onForkSuccess) {
        onForkSuccess(result.playbook_code);
      } else {
        router.push(`/workspaces/${targetWorkspaceId}/playbook/${result.playbook_code}`);
      }
    } catch (err) {
      console.error('Failed to fork playbook:', err);
      alert(err instanceof Error ? err.message : 'Failed to fork playbook');
    }
  };

  const getScopeLabel = (scope?: string) => {
    switch (scope) {
      case 'system':
        return 'System';
      case 'tenant':
        return 'Tenant';
      case 'profile':
        return 'Profile';
      case 'workspace':
        return 'Workspace';
      default:
        return 'Unknown';
    }
  };

  return (
    <>
      <button
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setShowForkDialog(true);
        }}
        disabled={forking}
        className="px-3 py-1 text-xs bg-purple-600 dark:bg-purple-700 text-white rounded hover:bg-purple-700 dark:hover:bg-purple-600 disabled:bg-gray-400 dark:disabled:bg-gray-600 disabled:cursor-not-allowed"
        title={t('forkPlaybookToWorkspace' as any)}
      >
        {forking ? t('forking' as any) : t('forkPlaybookToWorkspace' as any)}
      </button>

      {showForkDialog && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
          onClick={() => setShowForkDialog(false)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              setShowForkDialog(false);
            }
          }}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">
              {t('forkPlaybookDialog' as any)}
            </h2>

            <div className="mb-4">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                {t('playbook' as any)}: <span className="font-medium">{playbookName}</span>
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-500">
                {t('forkPlaybookDescription' as any)}
              </p>
            </div>

            {error && (
              <div className="mb-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
                <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
              </div>
            )}

            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('targetWorkspaceId' as any)}
              </label>
              <input
                type="text"
                value={targetWorkspaceId}
                onChange={(e) => setTargetWorkspaceId(e.target.value)}
                placeholder={t('targetWorkspaceId' as any)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              />
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                {t('targetWorkspaceIdDescription' as any)}
              </p>
            </div>

            <div className="flex items-center justify-end gap-3">
              <button
                onClick={() => setShowForkDialog(false)}
                disabled={forking}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-600 disabled:opacity-50"
              >
                {t('cancel' as any)}
              </button>
              <button
                onClick={handleFork}
                disabled={forking || !targetWorkspaceId.trim()}
                className="px-4 py-2 text-sm font-medium text-white bg-purple-600 rounded-md hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {forking ? t('forking' as any) : t('fork' as any)}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

