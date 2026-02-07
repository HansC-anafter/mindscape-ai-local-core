'use client';

import React, { useEffect, useState } from 'react';
import { LocalFilesystemManagerContent } from '@/app/settings/components/wizards/LocalFilesystemManagerContent';
import ResourceBindingPanel from '@/app/workspaces/[workspaceId]/components/ResourceBindingPanel';
import DataSourceOverlayPanel from '@/app/workspaces/[workspaceId]/components/DataSourceOverlayPanel';
import { t } from '@/lib/i18n';

interface Workspace {
  id: string;
  title: string;
  storage_base_path?: string;
  artifacts_dir?: string;
  storage_config?: any;
  playbook_storage_config?: Record<string, { base_path?: string; artifacts_dir?: string }>;
  execution_mode?: 'qa' | 'execution' | 'hybrid';
  expected_artifacts?: string[];
  execution_priority?: 'low' | 'medium' | 'high';
}

interface StoragePathConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  workspace: Workspace | null;
  workspaceId: string;
  apiUrl: string;
  onSuccess?: () => void;
}

const COMMON_ARTIFACTS = ['docx', 'pptx', 'xlsx', 'pdf', 'md', 'html'];

type TabType = 'storage' | 'results' | 'resources' | 'dataSources';

export default function StoragePathConfigModal({
  isOpen,
  onClose,
  workspace,
  workspaceId,
  apiUrl,
  onSuccess
}: StoragePathConfigModalProps) {
  const [workspaceData, setWorkspaceData] = useState<Workspace | null>(workspace);
  const [activeTab, setActiveTab] = useState<TabType>('storage');
  const [expectedArtifacts, setExpectedArtifacts] = useState<string[]>([]);
  const [originalExpectedArtifacts, setOriginalExpectedArtifacts] = useState<string[]>([]);
  const [savingExecution, setSavingExecution] = useState(false);
  const [executionError, setExecutionError] = useState<string | null>(null);
  const [executionSuccess, setExecutionSuccess] = useState(false);
  const [executionSettingsChanged, setExecutionSettingsChanged] = useState(false);
  // Fetch latest workspace data when modal opens
  useEffect(() => {
    if (isOpen && workspaceId) {
      const fetchWorkspace = async () => {
        try {
          const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}`);
          if (response.ok) {
            const data = await response.json();
            setWorkspaceData(data);
            const artifacts = data.expected_artifacts || [];
            setExpectedArtifacts(artifacts);
            setOriginalExpectedArtifacts(artifacts);
          }
        } catch (err) {
          console.error('Failed to fetch workspace data:', err);
          setWorkspaceData(workspace);
        }
      };
      fetchWorkspace();
    } else {
      setWorkspaceData(workspace);
    }
  }, [isOpen, workspaceId, apiUrl, workspace]);

  useEffect(() => {
    const changed =
      JSON.stringify(expectedArtifacts.sort()) !== JSON.stringify(originalExpectedArtifacts.sort());
    setExecutionSettingsChanged(changed);
  }, [expectedArtifacts, originalExpectedArtifacts]);

  const handleStorageConfigSuccess = () => {
    // Refresh workspace data after storage config save
    if (workspaceId && apiUrl) {
      fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}`)
        .then(res => res.json())
        .then(data => {
          setWorkspaceData(data);
        })
        .catch(err => console.error('Failed to refresh workspace:', err));
    }
    if (onSuccess) {
      onSuccess();
    }
  };

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    if (isOpen) {
      document.body.style.overflow = 'hidden';
      document.addEventListener('keydown', handleEscape);
      return () => {
        document.body.style.overflow = '';
        document.removeEventListener('keydown', handleEscape);
      };
    } else {
      document.body.style.overflow = '';
    }
  }, [isOpen, onClose]);

  const handleToggleArtifact = (artifact: string) => {
    setExpectedArtifacts(prev =>
      prev.includes(artifact)
        ? prev.filter(a => a !== artifact)
        : [...prev, artifact]
    );
  };

  const handleSaveExecutionSettings = async () => {
    setSavingExecution(true);
    setExecutionError(null);
    setExecutionSuccess(false);

    try {
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expected_artifacts: expectedArtifacts,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to update' }));
        throw new Error(errorData.detail || 'Failed to update execution settings');
      }

      const updated = await response.json();
      setOriginalExpectedArtifacts(updated.expected_artifacts || []);
      setExecutionSettingsChanged(false);
      setExecutionSuccess(true);
      setTimeout(() => setExecutionSuccess(false), 3000);

      if (onSuccess) {
        onSuccess();
      }
    } catch (err: any) {
      setExecutionError(err.message || '儲存失敗');
      console.error('Failed to save execution settings:', err);
    } finally {
      setSavingExecution(false);
    }
  };

  if (!isOpen) return null;

  const tabs: { id: TabType; label: string }[] = [
    { id: 'storage', label: t('configureWorkspaceStoragePath' as any) || '配置工作區儲存路徑' },
    { id: 'results', label: t('expectedArtifacts' as any) || '預期產出類型' },
    { id: 'resources', label: t('resourceBindings' as any) || '資源綁定' },
    { id: 'dataSources', label: t('dataSourceOverlaySettings' as any) || '資料來源覆寫' },
  ];

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
                  {t('fullSettings' as any) || '完整設置'}
                </h2>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                  {t('fullSettingsDescription' as any) || '管理資源綁定、工具覆寫和資料來源覆寫'}
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

            {/* Tabs */}
            <div className="flex border-b dark:border-gray-700 flex-shrink-0">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`
                    px-6 py-3 text-sm font-medium transition-colors
                    ${activeTab === tab.id
                      ? 'text-blue-600 dark:text-blue-400 border-b-2 border-blue-600 dark:border-blue-400 bg-blue-50 dark:bg-blue-900/20'
                      : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700/50'
                    }
                  `}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Content - Scrollable */}
            <div className="flex-1 overflow-y-auto">
              {activeTab === 'storage' && workspaceData && (
                <div className="p-6">
                  <LocalFilesystemManagerContent
                    onSuccess={handleStorageConfigSuccess}
                    workspaceMode={true}
                    workspaceId={workspaceId}
                    apiUrl={apiUrl}
                    workspaceTitle={workspaceData?.title}
                    initialStorageBasePath={workspaceData?.storage_base_path}
                    initialArtifactsDir={workspaceData?.artifacts_dir}
                    initialPlaybookStorageConfig={workspaceData?.playbook_storage_config}
                    showHeader={false}
                  />
                </div>
              )}

              {activeTab === 'results' && (
                <div className="p-6 space-y-4">
                  <div>
                    <h3 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
                      {t('expectedArtifacts' as any) || '預期產出類型'}
                    </h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                      {t('expectedArtifactsDescription' as any) || '選擇此 Workspace 預期產出的檔案類型, AI 會優先嘗試產出這些類型的文件。'}
                    </p>

                    <div className="flex flex-wrap gap-2 mb-4">
                      {COMMON_ARTIFACTS.map((artifact) => (
                        <button
                          key={artifact}
                          onClick={() => handleToggleArtifact(artifact)}
                          className={`
                            px-3 py-1.5 rounded-full text-sm transition-all
                            ${expectedArtifacts.includes(artifact)
                              ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-700'
                              : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700 hover:bg-gray-200 dark:hover:bg-gray-700'
                            }
                          `}
                        >
                          {artifact.toUpperCase()}
                        </button>
                      ))}
                    </div>

                    <div className="flex justify-end">
                      <button
                        onClick={handleSaveExecutionSettings}
                        disabled={savingExecution || !executionSettingsChanged}
                        className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
                      >
                        {savingExecution ? t('saving' as any) : t('saveSettings' as any)}
                      </button>
                    </div>

                    {executionError && (
                      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 mt-4">
                        <p className="text-sm text-red-700 dark:text-red-300">{executionError}</p>
                      </div>
                    )}

                    {executionSuccess && (
                      <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-3 mt-4">
                        <p className="text-sm text-green-700 dark:text-green-300">{t('success' as any)}</p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {activeTab === 'resources' && (
                <div className="p-6">
                  <ResourceBindingPanel workspaceId={workspaceId} />
                </div>
              )}

              {activeTab === 'dataSources' && (
                <div className="p-6">
                  <DataSourceOverlayPanel workspaceId={workspaceId} />
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
