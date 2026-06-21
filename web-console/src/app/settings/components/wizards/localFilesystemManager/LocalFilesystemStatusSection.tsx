'use client';

import { t } from '@/lib/i18n';
import { InlineAlert } from '@/app/settings/components/InlineAlert';

import type { DirectoryConfig } from './types';

interface LocalFilesystemStatusSectionProps {
  error: string | null;
  onClose?: () => void;
  onDismissError: () => void;
  onDismissSuccess: () => void;
  onRestart: () => void | Promise<void>;
  requiresRestart: boolean;
  restarting: boolean;
  showHeader: boolean;
  success: string | null;
  workspaceMode: boolean;
}

export function LocalFilesystemStatusSection({
  error,
  onClose,
  onDismissError,
  onDismissSuccess,
  onRestart,
  requiresRestart,
  restarting,
  showHeader,
  success,
  workspaceMode,
}: LocalFilesystemStatusSectionProps) {
  return (
    <>
      {showHeader && (
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
            {workspaceMode ? t('configureWorkspaceStoragePath' as any) : t('localFileSystemConfig' as any)}
          </h2>
          {onClose && (
            <button onClick={onClose} className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300">
              x
            </button>
          )}
        </div>
      )}

      {error && (
        <InlineAlert type="error" message={error} onDismiss={onDismissError} className="mb-4" />
      )}

      {success && (
        <div className="mb-4">
          <InlineAlert type="success" message={success} onDismiss={onDismissSuccess} className="mb-2" />
          {requiresRestart && (
            <div className="mt-3 p-3 bg-accent-10 dark:bg-blue-900/20 border border-accent/30 dark:border-blue-800 rounded-lg">
              <p className="text-sm text-accent dark:text-blue-300 mb-2">{t('restartRequired' as any)}</p>
              <button
                type="button"
                onClick={onRestart}
                disabled={restarting}
                className="px-4 py-2 bg-accent hover:bg-accent/90 disabled:bg-gray-400 text-white rounded-md text-sm font-medium transition-colors"
              >
                {restarting ? t('restarting' as any) : t('restartService' as any)}
              </button>
              <p className="text-xs text-accent dark:text-blue-400 mt-2">{t('orManuallyRun' as any)}</p>
            </div>
          )}
        </div>
      )}
    </>
  );
}

interface LocalFilesystemFooterSectionProps {
  directories: DirectoryConfig[];
  onClose?: () => void;
  onSave: () => void | Promise<void>;
  saving: boolean;
  showHeader: boolean;
}

export function LocalFilesystemFooterSection({
  directories,
  onClose,
  onSave,
  saving,
  showHeader,
}: LocalFilesystemFooterSectionProps) {
  return (
    <>
      {showHeader && (
        <div className="flex justify-end space-x-3 pt-4 border-t dark:border-gray-700 mt-4">
          {onClose && (
            <button
              onClick={onClose}
              className="px-4 py-2 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800"
            >
              {t('cancel' as any)}
            </button>
          )}
          <button
            onClick={onSave}
            disabled={saving || directories.length === 0}
            className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? t('saving' as any) : t('save' as any)}
          </button>
        </div>
      )}
    </>
  );
}
