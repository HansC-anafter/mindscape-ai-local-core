'use client';

import React, { useState, useEffect } from 'react';
import { createChangeSet, applyChangeSet, type ChangeSet } from '@/lib/lens-api';

interface ChangeSetBlockProps {
  sessionId: string;
  profileId: string;
  workspaceId?: string;
  onRefresh: () => void;
}

export function ChangeSetBlock({
  sessionId,
  profileId,
  workspaceId,
  onRefresh,
}: ChangeSetBlockProps) {
  const [changeset, setChangeset] = useState<ChangeSet | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [applyTo, setApplyTo] = useState<'session_only' | 'workspace' | 'preset'>('session_only');

  useEffect(() => {
    loadChangeset();
  }, [sessionId, profileId, workspaceId]);

  const loadChangeset = async () => {
    try {
      setIsLoading(true);
      const cs = await createChangeSet({
        profile_id: profileId,
        session_id: sessionId,
        workspace_id: workspaceId,
      });
      setChangeset(cs);
    } catch (error) {
      console.error('Failed to load changeset:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleApply = async () => {
    if (!changeset) return;

    if (applyTo === 'preset') {
      if (!confirm('這會改變你的全域預設，確定？')) {
        return;
      }
    }

    try {
      await applyChangeSet(changeset, applyTo, workspaceId);
      alert('變更已套用');
      onRefresh();
      loadChangeset();
    } catch (error) {
      console.error('Failed to apply changeset:', error);
      alert('Failed to apply changeset');
    }
  };

  if (isLoading) {
    return <div className="text-center py-4 text-sm text-gray-500">載入中...</div>;
  }

  if (!changeset || changeset.changes.length === 0) {
    return (
      <div className="text-center py-8 text-sm text-gray-500">
        目前沒有變更
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-gradient-to-r from-gray-50 to-blue-50 rounded-lg p-4 border border-gray-200 shadow-sm">
        <div className="flex items-center mb-2">
          <span className="text-lg mr-2">📝</span>
          <div className="text-sm font-semibold text-gray-900">變更摘要</div>
        </div>
        <div className="text-sm text-gray-700">{changeset.summary || '無變更'}</div>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold text-gray-700">變更列表</div>
          <span className="text-xs px-2 py-1 bg-gray-200 text-gray-600 rounded">
            {changeset.changes.length} 項
          </span>
        </div>
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {changeset.changes.map((change) => (
            <div
              key={change.node_id}
              className="bg-white rounded-lg p-3 border border-gray-200 shadow-sm hover:border-blue-300 transition-colors"
            >
              <div className="flex items-center justify-between mb-1">
                <div className="font-medium text-gray-900 text-sm">{change.node_label}</div>
                <div className="flex items-center space-x-1">
                  <span
                    className={`text-xs px-2 py-0.5 rounded ${
                      change.from_state === 'emphasize'
                        ? 'bg-yellow-100 text-yellow-700'
                        : change.from_state === 'keep'
                        ? 'bg-blue-100 text-blue-700'
                        : 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    {change.from_state}
                  </span>
                  <span className="text-gray-400">→</span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded ${
                      change.to_state === 'emphasize'
                        ? 'bg-yellow-100 text-yellow-700'
                        : change.to_state === 'keep'
                        ? 'bg-blue-100 text-blue-700'
                        : 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    {change.to_state}
                  </span>
                </div>
              </div>
              <div className="text-xs text-gray-500 mt-1">ID: {change.node_id.slice(0, 8)}...</div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">套用到</label>
        <select
          value={applyTo}
          onChange={(e) => setApplyTo(e.target.value as any)}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="session_only">Session Only（不保存）</option>
          <option value="workspace">Workspace（保存到工作區）</option>
          <option value="preset">Preset（保存到全域預設）</option>
        </select>
      </div>

      <button
        onClick={handleApply}
        className="w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
      >
        套用變更
      </button>
    </div>
  );
}

