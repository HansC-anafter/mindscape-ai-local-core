'use client';

import React, { useState } from 'react';
import { useWorkspaceOverrides, setWorkspaceOverride, removeWorkspaceOverride } from '@/lib/lens-api';
import type { LensNodeState } from '@/lib/lens-api';

interface WorkspaceOverridePanelProps {
  workspaceId: string;
  profileId: string;
  onRefresh?: () => void;
}

export function WorkspaceOverridePanel({
  workspaceId,
  profileId,
  onRefresh,
}: WorkspaceOverridePanelProps) {
  const { overrides, isLoading, refresh } = useWorkspaceOverrides(workspaceId);
  const [editingNodeId, setEditingNodeId] = useState<string | null>(null);
  const [newState, setNewState] = useState<LensNodeState>('keep');

  const handleSetOverride = async (nodeId: string, state: LensNodeState) => {
    try {
      await setWorkspaceOverride(workspaceId, nodeId, state);
      await refresh();
      onRefresh?.();
    } catch (error) {
      console.error('Failed to set override:', error);
      alert('設置覆寫失敗');
    }
  };

  const handleRemoveOverride = async (nodeId: string) => {
    if (!confirm('確定要移除這個覆寫嗎？')) return;

    try {
      await removeWorkspaceOverride(workspaceId, nodeId);
      await refresh();
      onRefresh?.();
    } catch (error) {
      console.error('Failed to remove override:', error);
      alert('移除覆寫失敗');
    }
  };

  if (isLoading) {
    return (
      <div className="text-center py-4 text-sm text-gray-500">載入中...</div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900">
          Workspace 覆寫 ({overrides?.length || 0})
        </h3>
        <button
          onClick={() => refresh()}
          className="text-xs text-blue-600 hover:text-blue-800"
        >
          刷新
        </button>
      </div>

      {!overrides || overrides.length === 0 ? (
        <div className="text-center py-4 text-sm text-gray-500">
          目前沒有 Workspace 覆寫
        </div>
      ) : (
        <div className="space-y-2">
          {overrides.map((override) => (
            <div
              key={override.node_id}
              className="p-3 bg-gray-50 rounded-lg border border-gray-200"
            >
              <div className="flex items-center justify-between mb-2">
                <div>
                  <div className="text-sm font-medium text-gray-900">
                    {override.node_id.slice(0, 12)}...
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    狀態: {override.state === 'emphasize' ? '強調' : override.state === 'keep' ? '保持' : '關閉'}
                  </div>
                </div>
                <div className="flex items-center space-x-2">
                  {editingNodeId === override.node_id ? (
                    <>
                      <select
                        value={newState}
                        onChange={(e) => setNewState(e.target.value as LensNodeState)}
                        className="text-xs border border-gray-300 rounded px-2 py-1"
                      >
                        <option value="off">關閉</option>
                        <option value="keep">保持</option>
                        <option value="emphasize">強調</option>
                      </select>
                      <button
                        onClick={() => {
                          handleSetOverride(override.node_id, newState);
                          setEditingNodeId(null);
                        }}
                        className="text-xs px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700"
                      >
                        保存
                      </button>
                      <button
                        onClick={() => setEditingNodeId(null)}
                        className="text-xs px-2 py-1 bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
                      >
                        取消
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={() => {
                          setEditingNodeId(override.node_id);
                          setNewState(override.state);
                        }}
                        className="text-xs px-2 py-1 bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
                      >
                        編輯
                      </button>
                      <button
                        onClick={() => handleRemoveOverride(override.node_id)}
                        className="text-xs px-2 py-1 bg-red-100 text-red-700 rounded hover:bg-red-200"
                      >
                        移除
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

