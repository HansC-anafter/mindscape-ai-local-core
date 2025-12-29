'use client';

import React, { useState, useEffect } from 'react';
import { useEffectiveLens, useLensProfiles, createChangeSet, type ChangeSet, type MindLensProfile } from '@/lib/lens-api';
import { ScopeIndicator } from './ScopeIndicator';
import { PresetDiffView } from './PresetDiffView';
import { PresetCard } from './PresetCard';
import { WorkspaceOverridePanel } from './WorkspaceOverridePanel';

interface PresetPanelProps {
  activePreset: { id: string; name: string } | null;
  sessionId: string;
  profileId: string;
  workspaceId?: string;
  onPresetSelect: (id: string) => void;
  onRefresh: () => void;
}

interface ErrorState {
  message: string;
  type: 'error' | 'warning' | 'info';
}

interface DirtyState {
  patches: PendingPatch[];
  isDirty: boolean;
}

interface PendingPatch {
  node_id: string;
  from: string;
  to: string;
  timestamp: number;
}

export function PresetPanel({
  activePreset,
  sessionId,
  profileId,
  workspaceId,
  onPresetSelect,
  onRefresh,
}: PresetPanelProps) {
  const [dirtyState, setDirtyState] = useState<DirtyState>({ patches: [], isDirty: false });
  const [changeset, setChangeset] = useState<ChangeSet | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ErrorState | null>(null);
  const [showPresetList, setShowPresetList] = useState(false);
  const [diffPresetId, setDiffPresetId] = useState<string | null>(null);

  const { profiles, isLoading: profilesLoading, refresh: refreshProfiles } = useLensProfiles(profileId);

  const { lens } = useEffectiveLens({
    profile_id: profileId,
    workspace_id: workspaceId,
    session_id: sessionId,
  });

  useEffect(() => {
    if (lens && lens.session_override_count > 0) {
      loadChangeset();
    } else {
      setDirtyState({ patches: [], isDirty: false });
      setChangeset(null);
    }
  }, [lens, sessionId, profileId, workspaceId]);

  const loadChangeset = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const cs = await createChangeSet({
        profile_id: profileId,
        session_id: sessionId,
        workspace_id: workspaceId,
      });
      setChangeset(cs);
      setDirtyState({
        patches: cs.changes.map((c) => ({
          node_id: c.node_id,
          from: c.from_state,
          to: c.to_state,
          timestamp: Date.now(),
        })),
        isDirty: cs.changes.length > 0,
      });
    } catch (error: any) {
      console.error('Failed to load changeset:', error);
      setError({
        message: error.message || 'Failed to load changeset',
        type: 'error',
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleSave = async () => {
    if (!changeset || !workspaceId) {
      setError({
        message: 'Workspace ID is required',
        type: 'warning',
      });
      return;
    }
    try {
      setIsLoading(true);
      setError(null);
      const { applyChangeSet } = await import('@/lib/lens-api');
      await applyChangeSet(changeset, 'workspace', workspaceId);
      setError({
        message: '已保存到 Workspace',
        type: 'info',
      });
      setTimeout(() => setError(null), 3000);
      onRefresh();
      await loadChangeset();
    } catch (error: any) {
      console.error('Failed to save:', error);
      setError({
        message: error.message || '保存失敗',
        type: 'error',
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleSaveAs = async (name: string) => {
    if (!confirm(`確定要將當前狀態創建為新的 Preset "${name}" 嗎？`)) {
      return;
    }
    try {
      setIsLoading(true);
      setError(null);
      const { createPresetSnapshot } = await import('@/lib/lens-api');
      await createPresetSnapshot({
        profile_id: profileId,
        name: name,
        workspace_id: workspaceId,
        session_id: sessionId,
        description: `從當前狀態創建的快照`
      });
      setError({
        message: `已創建 Preset "${name}"`,
        type: 'info',
      });
      setTimeout(() => setError(null), 3000);
      onRefresh();
      await loadChangeset();
      refreshProfiles();
    } catch (error: any) {
      console.error('Failed to create preset snapshot:', error);
      setError({
        message: error.message || '創建失敗',
        type: 'error',
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = async () => {
    if (confirm('確定要重置所有變更嗎？')) {
      try {
        setIsLoading(true);
        setError(null);
        const { clearSessionOverrides } = await import('@/lib/lens-api');
        await clearSessionOverrides(sessionId);
        onRefresh();
        setDirtyState({ patches: [], isDirty: false });
        setChangeset(null);
        setError({
          message: '已重置所有變更',
          type: 'info',
        });
        setTimeout(() => setError(null), 3000);
      } catch (error: any) {
        console.error('Failed to reset:', error);
        setError({
          message: error.message || '重置失敗',
          type: 'error',
        });
      } finally {
        setIsLoading(false);
      }
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 h-full flex flex-col">
      <div className="p-4 border-b border-gray-200">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">Preset</h2>
          <button
            onClick={() => setShowPresetList(!showPresetList)}
            className="text-sm text-blue-600 hover:text-blue-800"
          >
            {showPresetList ? '隱藏' : '選擇'}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Error Message */}
        {error && (
          <div
            className={`rounded-lg p-3 border text-sm ${
              error.type === 'error'
                ? 'bg-red-50 border-red-200 text-red-800'
                : error.type === 'warning'
                ? 'bg-yellow-50 border-yellow-200 text-yellow-800'
                : 'bg-blue-50 border-blue-200 text-blue-800'
            }`}
          >
            {error.message}
          </div>
        )}

        {/* Preset List */}
        {showPresetList && (
          <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
            <div className="text-sm font-medium text-gray-900 mb-2">選擇 Preset</div>
            {profilesLoading ? (
              <div className="text-xs text-gray-500">載入中...</div>
            ) : profiles.length === 0 ? (
              <div className="text-xs text-gray-500">沒有可用的 Preset</div>
            ) : (
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {profiles.map((profile) => (
                  <PresetCard
                    key={profile.id}
                    profile={profile}
                    activePresetId={activePreset?.id}
                    onSelect={(id) => {
                      onPresetSelect(id);
                      setShowPresetList(false);
                    }}
                    onViewDiff={(id) => setDiffPresetId(id)}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Active Preset */}
        {activePreset && (
          <div className="bg-blue-50 rounded-lg p-3 border border-blue-200 space-y-3">
            <div>
              <div className="text-xs font-medium text-blue-800 mb-1">目前使用</div>
              <div className="text-sm font-semibold text-blue-900">{activePreset.name}</div>
              <div className="text-xs text-blue-700 mt-1">ID: {activePreset.id}</div>
            </div>

            {/* Scope Indicator */}
            <div className="pt-2 border-t border-blue-200">
              <ScopeIndicator effectiveLens={lens} />
            </div>
          </div>
        )}

        {/* Dirty State */}
        {dirtyState.isDirty && (
          <div className="bg-yellow-50 rounded-lg p-3 border border-yellow-200">
            <div className="text-sm font-medium text-yellow-900 mb-2">
              未保存的變更 ({dirtyState.patches.length})
            </div>
            <div className="space-y-1 max-h-32 overflow-y-auto">
              {dirtyState.patches.map((patch) => (
                <div key={patch.node_id} className="text-xs text-yellow-800">
                  <span className="font-medium">{patch.node_id.slice(0, 8)}</span>:{' '}
                  {patch.from} → {patch.to}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Changeset Summary */}
        {changeset && (
          <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
            <div className="text-sm font-medium text-gray-900 mb-1">變更摘要</div>
            <div className="text-xs text-gray-600">{changeset.summary}</div>
          </div>
        )}

        {isLoading && (
          <div className="text-center py-4 text-sm text-gray-500">載入中...</div>
        )}

        {/* Preset Diff View */}
        {diffPresetId && activePreset && (
          <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
            <PresetDiffView
              presetAId={activePreset.id}
              presetBId={diffPresetId}
              onClose={() => setDiffPresetId(null)}
            />
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="p-4 border-t border-gray-200 space-y-2">
        {dirtyState.isDirty && (
          <>
            <button
              onClick={handleSave}
              className="w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm font-medium"
            >
              保存到 Workspace
            </button>
            <button
              onClick={() => {
                const name = prompt('輸入新 Preset 名稱：');
                if (name) handleSaveAs(name);
              }}
              className="w-full px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 text-sm font-medium"
            >
              創建快照
            </button>
            <button
              onClick={handleReset}
              className="w-full px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 text-sm font-medium"
            >
              重置變更
            </button>
          </>
        )}
      </div>
    </div>
  );
}

