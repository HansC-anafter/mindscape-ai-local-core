'use client';

import React from 'react';
import useSWR from 'swr';
import { getApiBaseUrl } from '@/lib/api-url';
import type { PresetDiff } from '@/lib/lens-api';

interface PresetDiffViewProps {
  presetAId: string;
  presetBId: string;
  onClose?: () => void;
}

const fetcher = async (url: string) => {
  const res = await fetch(url);
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to fetch' }));
    throw new Error(error.detail || `Failed to fetch: ${res.status}`);
  }
  return res.json();
};

export function PresetDiffView({
  presetAId,
  presetBId,
  onClose,
}: PresetDiffViewProps) {
  const { data: diff, isLoading, error } = useSWR<PresetDiff>(
    presetAId && presetBId
      ? `${getApiBaseUrl()}/api/v1/mindscape/lens/profiles/${presetAId}/diff?compare_with=${presetBId}`
      : null,
    fetcher
  );

  if (isLoading) {
    return (
      <div className="text-center py-4 text-sm text-gray-500">載入中...</div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-4 text-sm text-red-500">
        無法載入差異: {error.message}
      </div>
    );
  }

  if (!diff) {
    return (
      <div className="text-center py-4 text-sm text-gray-500">
        無法載入差異
      </div>
    );
  }

  // 按变化类型分组
  const strengthened = diff.changes.filter(c => c.change_type === 'strengthened');
  const weakened = diff.changes.filter(c => c.change_type === 'weakened');
  const disabled = diff.changes.filter(c => c.change_type === 'disabled');
  const enabled = diff.changes.filter(c => c.change_type === 'enabled');
  const changed = diff.changes.filter(c => c.change_type === 'changed');

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-gray-900">
            {diff.preset_a_name} vs {diff.preset_b_name}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            {diff.changes.length} 個差異
          </div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="text-xs text-gray-500 hover:text-gray-700"
          >
            ✕
          </button>
        )}
      </div>

      {/* Summary */}
      {diff.changes.length === 0 ? (
        <div className="text-center py-4 text-sm text-gray-500">
          無差異
        </div>
      ) : (
        <div className="space-y-3">
          {/* Strengthened */}
          {strengthened.length > 0 && (
            <div className="bg-green-50 rounded-lg p-3 border border-green-200">
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm font-semibold text-green-700">
                  + 強化 ({strengthened.length})
                </div>
              </div>
              <div className="space-y-1">
                {strengthened.map(change => (
                  <div
                    key={change.node_id}
                    className="text-sm text-gray-700 flex items-center justify-between"
                  >
                    <span>{change.node_label}</span>
                    <span className="text-xs text-gray-500">
                      {change.from_state} → {change.to_state}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Weakened */}
          {weakened.length > 0 && (
            <div className="bg-yellow-50 rounded-lg p-3 border border-yellow-200">
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm font-semibold text-yellow-700">
                  - 弱化 ({weakened.length})
                </div>
              </div>
              <div className="space-y-1">
                {weakened.map(change => (
                  <div
                    key={change.node_id}
                    className="text-sm text-gray-700 flex items-center justify-between"
                  >
                    <span>{change.node_label}</span>
                    <span className="text-xs text-gray-500">
                      {change.from_state} → {change.to_state}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Disabled */}
          {disabled.length > 0 && (
            <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm font-semibold text-gray-700">
                  ○ 關閉 ({disabled.length})
                </div>
              </div>
              <div className="space-y-1">
                {disabled.map(change => (
                  <div
                    key={change.node_id}
                    className="text-sm text-gray-700 flex items-center justify-between"
                  >
                    <span>{change.node_label}</span>
                    <span className="text-xs text-gray-500">
                      {change.from_state} → {change.to_state}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Enabled */}
          {enabled.length > 0 && (
            <div className="bg-blue-50 rounded-lg p-3 border border-blue-200">
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm font-semibold text-blue-700">
                  + 啟用 ({enabled.length})
                </div>
              </div>
              <div className="space-y-1">
                {enabled.map(change => (
                  <div
                    key={change.node_id}
                    className="text-sm text-gray-700 flex items-center justify-between"
                  >
                    <span>{change.node_label}</span>
                    <span className="text-xs text-gray-500">
                      {change.from_state} → {change.to_state}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Changed (other) */}
          {changed.length > 0 && (
            <div className="bg-purple-50 rounded-lg p-3 border border-purple-200">
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm font-semibold text-purple-700">
                  ↻ 其他變更 ({changed.length})
                </div>
              </div>
              <div className="space-y-1">
                {changed.map(change => (
                  <div
                    key={change.node_id}
                    className="text-sm text-gray-700 flex items-center justify-between"
                  >
                    <span>{change.node_label}</span>
                    <span className="text-xs text-gray-500">
                      {change.from_state} → {change.to_state}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

