'use client';

import React, { useState } from 'react';
import useSWR from 'swr';
import { getApiBaseUrl } from '@/lib/api-url';
import type { LensNode } from '@/lib/lens-api';

interface NodeDetailPanelProps {
  node: LensNode | null;
  onClose: () => void;
  profileId: string;
  workspaceId?: string;
}

interface NodeEvidence {
  node_id: string;
  execution_id: string;
  workspace_id: string;
  triggered_at: string;
  contribution?: string;
}

const fetcher = async (url: string) => {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch: ${res.status}`);
  }
  return res.json();
};

export function NodeDetailPanel({
  node,
  onClose,
  profileId,
  workspaceId,
}: NodeDetailPanelProps) {
  const [activeTab, setActiveTab] = useState<'info' | 'evidence' | 'playbooks'>('info');

  // 获取节点证据
  const { data: evidenceData, isLoading: evidenceLoading } = useSWR<{ evidence: NodeEvidence[] }>(
    node
      ? `${getApiBaseUrl()}/api/v1/mindscape/lens/evidence/nodes/${node.node_id}?profile_id=${profileId}${workspaceId ? `&workspace_id=${workspaceId}` : ''}&limit=10`
      : null,
    fetcher,
    { revalidateOnFocus: false }
  );

  if (!node) {
    return null;
  }

  return (
    <div className="fixed inset-y-0 right-0 w-96 bg-white shadow-xl border-l border-gray-200 z-50 flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-gray-200 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">節點詳情</h2>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600"
        >
          ✕
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {/* Tabs */}
        <div className="border-b border-gray-200">
          <div className="flex">
            <button
              onClick={() => setActiveTab('info')}
              className={`flex-1 px-4 py-2 text-sm font-medium ${
                activeTab === 'info'
                  ? 'border-b-2 border-blue-600 text-blue-600'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              資訊
            </button>
            <button
              onClick={() => setActiveTab('evidence')}
              className={`flex-1 px-4 py-2 text-sm font-medium ${
                activeTab === 'evidence'
                  ? 'border-b-2 border-blue-600 text-blue-600'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              證據 ({evidenceData?.evidence?.length || 0})
            </button>
            <button
              onClick={() => setActiveTab('playbooks')}
              className={`flex-1 px-4 py-2 text-sm font-medium ${
                activeTab === 'playbooks'
                  ? 'border-b-2 border-blue-600 text-blue-600'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Playbooks
            </button>
          </div>
        </div>

        {/* Tab Content */}
        <div className="p-4">
          {activeTab === 'info' && (
            <div className="space-y-4">
              <div>
                <h3 className="text-sm font-semibold text-gray-900 mb-1">節點標籤</h3>
                <p className="text-sm text-gray-700">{node.node_label}</p>
              </div>

              <div>
                <h3 className="text-sm font-semibold text-gray-900 mb-1">類型</h3>
                <p className="text-sm text-gray-700">{node.node_type}</p>
              </div>

              <div>
                <h3 className="text-sm font-semibold text-gray-900 mb-1">分類</h3>
                <p className="text-sm text-gray-700">{node.category}</p>
              </div>

              <div>
                <h3 className="text-sm font-semibold text-gray-900 mb-1">狀態</h3>
                <span
                  className={`inline-block px-2 py-1 rounded text-xs font-medium ${
                    node.state === 'emphasize'
                      ? 'bg-green-100 text-green-700'
                      : node.state === 'keep'
                      ? 'bg-blue-100 text-blue-700'
                      : 'bg-gray-100 text-gray-700'
                  }`}
                >
                  {node.state === 'emphasize' ? '強調' : node.state === 'keep' ? '保持' : '關閉'}
                </span>
              </div>


              {node.effective_scope && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-900 mb-1">有效範圍</h3>
                  <p className="text-sm text-gray-700">{node.effective_scope}</p>
                </div>
              )}
            </div>
          )}

          {activeTab === 'evidence' && (
            <div className="space-y-3">
              {evidenceLoading ? (
                <div className="text-center py-4 text-sm text-gray-500">載入中...</div>
              ) : evidenceData?.evidence && evidenceData.evidence.length > 0 ? (
                evidenceData.evidence.map((evidence, idx) => (
                  <div
                    key={idx}
                    className="p-3 bg-gray-50 rounded-lg border border-gray-200"
                  >
                    <div className="text-xs text-gray-500 mb-1">
                      {new Date(evidence.triggered_at).toLocaleString('zh-TW')}
                    </div>
                    {evidence.contribution && (
                      <div className="text-sm text-gray-700">{evidence.contribution}</div>
                    )}
                    <div className="text-xs text-gray-500 mt-1">
                      Execution: {evidence.execution_id.slice(0, 8)}...
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-4 text-sm text-gray-500">
                  目前沒有證據記錄
                </div>
              )}
            </div>
          )}

          {activeTab === 'playbooks' && (
            <div className="space-y-3">
              <div className="text-center py-4 text-sm text-gray-500">
                Playbook 連結功能開發中...
              </div>
              {/* TODO: 实现 Playbook 链接显示 */}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

