'use client';

import React, { useState } from 'react';
import StoragePathConfigModal from '@/components/StoragePathConfigModal';
import { getApiBaseUrl } from '../../../lib/api-url';

interface DataSource {
  local_folder?: string;
  obsidian_vault?: string;
  wordpress?: string;
  rag_source?: string;
}

interface Workspace {
  id: string;
  title: string;
  storage_base_path?: string;
  artifacts_dir?: string;
  storage_config?: any;
}

interface WorkspaceScopePanelProps {
  dataSources?: DataSource | null;
  workspaceId: string;
  apiUrl?: string;
  workspace?: Workspace | null;
}

export default function WorkspaceScopePanel({
  dataSources,
  workspaceId,
  apiUrl = getApiBaseUrl(),
  workspace,
}: WorkspaceScopePanelProps) {
  const [showStorageModal, setShowStorageModal] = useState(false);

  const handleManageDataSources = () => {
    setShowStorageModal(true);
  };

  return (
    <div className="p-2">
      {/* Data Sources Card - Compact Layout */}
      <div className="bg-surface-secondary dark:bg-gray-800 border border-default dark:border-gray-700 rounded-lg p-2 shadow-sm">
        <div className="flex items-center justify-between mb-1.5">
          <h3 className="text-xs font-semibold text-primary dark:text-gray-100">
            資料來源
          </h3>
          <button
            onClick={handleManageDataSources}
            className="text-xs text-accent dark:text-blue-400 hover:opacity-80 dark:hover:text-blue-300 font-medium"
          >
            管理
          </button>
        </div>

        <div className="space-y-1 text-[10px] text-primary dark:text-gray-300">
          {dataSources?.local_folder && (
            <div className="flex items-center">
              <span className="mr-1.5">📁</span>
              <span>
                <span className="font-medium">本地資料夾:</span>{' '}
                <span className="text-secondary dark:text-gray-400">{dataSources.local_folder}</span>
              </span>
            </div>
          )}

          {dataSources?.obsidian_vault && (
            <div className="flex items-center">
              <span className="mr-1.5">🗂</span>
              <span>
                <span className="font-medium">Obsidian vault:</span>{' '}
                <span className="text-gray-600 dark:text-gray-400">{dataSources.obsidian_vault}</span>
              </span>
            </div>
          )}

          {dataSources?.wordpress && (
            <div className="flex items-center">
              <span className="mr-1.5">🌐</span>
              <span>
                <span className="font-medium">WordPress:</span>{' '}
                <span className="text-gray-600 dark:text-gray-400">{dataSources.wordpress}</span>
                <span className="ml-1.5 text-green-600 dark:text-green-400">(已連線)</span>
              </span>
            </div>
          )}

          {dataSources?.rag_source && (
            <div className="flex items-center">
              <span className="mr-1.5">🔍</span>
              <span>
                <span className="font-medium">RAG 來源:</span>{' '}
                <span className="text-gray-600 dark:text-gray-400">{dataSources.rag_source}</span>
              </span>
            </div>
          )}

          {!dataSources ||
            (!dataSources.local_folder &&
              !dataSources.obsidian_vault &&
              !dataSources.wordpress &&
              !dataSources.rag_source) && (
              <div className="text-gray-500 dark:text-gray-400 italic text-[10px]">
                尚未配置資料來源
              </div>
            )}
        </div>
      </div>

      {/* Storage Config Modal */}
      <StoragePathConfigModal
        isOpen={showStorageModal}
        onClose={() => setShowStorageModal(false)}
        workspace={workspace ?? null}
        workspaceId={workspaceId}
        apiUrl={apiUrl}
        onSuccess={() => {
          // Trigger workspace update event
          window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
        }}
      />
    </div>
  );
}
