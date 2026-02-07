'use client';

import React, { useEffect } from 'react';
import WorkspaceSettings from './WorkspaceSettings';
import { t } from '@/lib/i18n';

interface Workspace {
  id: string;
  title: string;
  storage_base_path?: string;
  artifacts_dir?: string;
  storage_config?: any;
  execution_mode?: 'qa' | 'execution' | 'hybrid';
  expected_artifacts?: string[];
  execution_priority?: 'low' | 'medium' | 'high';
}

interface WorkspaceSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  workspace: Workspace | null;
  workspaceId: string;
  apiUrl: string;
  onUpdate?: () => void;
}

export default function WorkspaceSettingsModal({
  isOpen,
  onClose,
  workspace,
  workspaceId,
  apiUrl,
  onUpdate,
}: WorkspaceSettingsModalProps) {
  // Prevent body scroll when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  // Handle Escape key
  useEffect(() => {
    if (!isOpen) return;

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleEscape);
    return () => {
      window.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="workspace-settings-modal-title"
    >
      <div
        className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-6xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b dark:border-gray-700 flex-shrink-0">
          <div>
            <h2
              id="workspace-settings-modal-title"
              className="text-2xl font-semibold text-gray-900 dark:text-gray-100"
            >
              {t('fullSettings' as any)}
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {t('fullSettingsDescription' as any)}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
            aria-label={t('close' as any)}
          >
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Content - Scrollable */}
        <div className="flex-1 overflow-y-auto p-6">
          {workspace ? (
            <WorkspaceSettings
              workspace={workspace}
              workspaceId={workspaceId}
              apiUrl={apiUrl}
              onUpdate={() => {
                if (onUpdate) {
                  onUpdate();
                }
              }}
            />
          ) : (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              {t('loading' as any) || '載入中...'}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end p-6 border-t dark:border-gray-700 flex-shrink-0">
          <button
            onClick={onClose}
            className="px-6 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 transition-colors"
          >
            {t('close' as any)}
          </button>
        </div>
      </div>
    </div>
  );
}

