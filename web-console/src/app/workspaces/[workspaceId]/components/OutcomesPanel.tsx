'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useConflictHandler } from '@/hooks/useConflictHandler';
import ConflictDialog from '@/components/ConflictDialog';
import { useToast } from '@/components/Toast';
import { t } from '@/lib/i18n';

interface Artifact {
  id: string;
  workspace_id: string;
  intent_id?: string;
  task_id?: string;
  execution_id?: string;
  playbook_code: string;
  artifact_type: string;
  title: string;
  summary: string;
  content: any;
  storage_ref?: string;
  sync_state?: string;
  primary_action_type: string;
  metadata: any;
  created_at: string;
  updated_at: string;
}

interface OutcomesPanelProps {
  workspaceId: string;
  apiUrl: string;
  onArtifactClick?: (artifact: Artifact) => void;
}

export type { Artifact };

const getArtifactIcon = (artifactType: string): string => {
  const iconMap: Record<string, string> = {
    checklist: '✅',
    draft: '📝',
    config: '⚙️',
    canva: '🎨',
    audio: '🔊',
    docx: '📄'
  };
  return iconMap[artifactType] || '📦';
};

export default function OutcomesPanel({
  workspaceId,
  apiUrl,
  onArtifactClick
}: OutcomesPanelProps) {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [highlightedArtifactIds, setHighlightedArtifactIds] = useState<Set<string>>(new Set());
  const previousArtifactsRef = useRef<Artifact[]>([]);
  const { conflictDialog, handleConflict, closeConflictDialog } = useConflictHandler();
  const { showToast, ToastComponent } = useToast();

  const loadArtifacts = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts?limit=100`);
      if (!response.ok) {
        throw new Error(`Failed to load artifacts: ${response.statusText}`);
      }
      const data = await response.json();
      const newArtifacts = data.artifacts || [];

      // Detect newly added artifacts (compare before and after lists)
      if (previousArtifactsRef.current.length > 0) {
        const previousIds = new Set(previousArtifactsRef.current.map(a => a.id));
        const newArtifactsList = newArtifacts.filter((a: Artifact) => !previousIds.has(a.id));

        if (newArtifactsList.length > 0) {
          // Show Toast notification
          if (newArtifactsList.length === 1) {
            const newArtifact = newArtifactsList[0];
            showToast({
              message: `✅ 已新增 1 個成果：『${newArtifact.title}』`,
              type: 'success',
              duration: 5000,
              action: onArtifactClick ? {
                label: '打開成果卡',
                onClick: () => onArtifactClick(newArtifact)
              } : undefined
            });
          } else {
            showToast({
              message: `✅ 已新增 ${newArtifactsList.length} 個成果`,
              type: 'success',
              duration: 5000
            });
          }

          // Highlight newly added artifacts
          const newIds = new Set<string>(newArtifactsList.map((a: Artifact) => a.id));
          setHighlightedArtifactIds(newIds);

          // Remove highlight after 5 seconds
          setTimeout(() => {
            setHighlightedArtifactIds(new Set());
          }, 5000);
        }
      }

      setArtifacts(newArtifacts);
      previousArtifactsRef.current = newArtifacts;
    } catch (err) {
      console.error('Failed to load artifacts:', err);
      setError(err instanceof Error ? err.message : 'Failed to load artifacts');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Load artifacts on mount
    loadArtifacts();

    // Debounce timer for batching multiple events
    let debounceTimer: NodeJS.Timeout | null = null;
    let isPending = false;
    let timeoutTimer: NodeJS.Timeout | null = null;
    let lastRefreshTime = Date.now();

    // 5 second timeout fallback: if no refresh for 5 seconds, force refresh
    const setupTimeoutRefresh = () => {
      if (timeoutTimer) {
        clearTimeout(timeoutTimer);
      }
      timeoutTimer = setTimeout(() => {
        const timeSinceLastRefresh = Date.now() - lastRefreshTime;
        if (timeSinceLastRefresh >= 5000 && !isPending) {
          console.log('OutcomesPanel: Timeout backup refresh triggered');
          isPending = true;
          loadArtifacts().finally(() => {
            isPending = false;
            lastRefreshTime = Date.now();
          });
        }
      }, 5000);
    };

    // Listen for workspace chat updates to refresh artifacts
    const handleChatUpdate = () => {
      console.log('OutcomesPanel: Received workspace-chat-updated event, scheduling refresh');
      lastRefreshTime = Date.now();
      // Debounce: only trigger load after 1 second of no events
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }
      debounceTimer = setTimeout(() => {
        if (!isPending) {
          isPending = true;
          loadArtifacts().finally(() => {
            isPending = false;
            lastRefreshTime = Date.now();
            setupTimeoutRefresh(); // Reset timeout
          });
        }
      }, 1000);
      setupTimeoutRefresh(); // Set timeout fallback
    };

    // Initial timeout setup
    setupTimeoutRefresh();

    window.addEventListener('workspace-chat-updated', handleChatUpdate);
    return () => {
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }
      if (timeoutTimer) {
        clearTimeout(timeoutTimer);
      }
      window.removeEventListener('workspace-chat-updated', handleChatUpdate);
    };
  }, [workspaceId, apiUrl]);

  const handleManualRefresh = async () => {
    try {
      await loadArtifacts();
      showToast({
        message: '✅ 已刷新成果列表',
        type: 'success',
        duration: 2000
      });
    } catch (err) {
      showToast({
        message: '❌ 刷新失敗，請稍後再試',
        type: 'error',
        duration: 3000
      });
    }
  };

  const handleArtifactClick = (artifact: Artifact) => {
    if (onArtifactClick) {
      onArtifactClick(artifact);
    }
  };

  const handleCopy = async (artifact: Artifact, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts/${artifact.id}/copy`,
        { method: 'POST' }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        // Check for conflict
        await handleConflict(
          { ...errorData, status: response.status },
          async () => {
            // Retry with force=true (if API supports it)
            const retryResponse = await fetch(
              `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts/${artifact.id}/copy?force=true`,
              { method: 'POST' }
            );
            if (!retryResponse.ok) {
              throw new Error('Failed to copy artifact');
            }
            return await retryResponse.json();
          },
          async (data) => {
            await navigator.clipboard.writeText(data.content);
            showToast({
              message: '已複製到剪貼板',
              type: 'success',
              duration: 3000
            });
          },
          (err) => {
            console.error('Failed to copy artifact:', err);
            showToast({
              message: '複製失敗，請重試',
              type: 'error',
              duration: 3000
            });
          }
        );
        return;
      }

      const data = await response.json();
      await navigator.clipboard.writeText(data.content);
      showToast({
        message: '已複製到剪貼板',
        type: 'success',
        duration: 3000
      });
    } catch (err) {
      console.error('Failed to copy artifact:', err);
      showToast({
        message: '複製失敗，請重試',
        type: 'error',
        duration: 3000
      });
    }
  };

  const handleOpenExternal = async (artifact: Artifact, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts/${artifact.id}/external-url`
      );
      if (!response.ok) {
        throw new Error('Failed to get external URL');
      }
      const data = await response.json();
      window.open(data.url, '_blank');
    } catch (err) {
      console.error('Failed to open external URL:', err);
      showToast({
        message: '開啟失敗，請重試',
        type: 'error',
        duration: 3000
      });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-sm text-gray-500 dark:text-gray-400">{t('loading') || '載入中...'}</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-sm text-red-500 dark:text-red-400">{t('error') || '錯誤'}: {error}</div>
      </div>
    );
  }

  if (artifacts.length === 0) {
    return (
      <div className="flex items-center justify-center h-full px-2">
        <div className="text-xs text-gray-500 dark:text-gray-400">{t('noOutcomes') || '尚無成果'}</div>
      </div>
    );
  }

  return (
    <>
      {/* Toast Container */}
      <ToastComponent />

      {/* Conflict Dialog */}
      {conflictDialog && (
        <ConflictDialog
          isOpen={conflictDialog.isOpen}
          conflict={conflictDialog.conflict}
          onConfirm={conflictDialog.onConfirm}
          onCancel={conflictDialog.onCancel}
          onUseNewVersion={conflictDialog.onUseNewVersion}
        />
      )}

      <div className="h-full overflow-y-auto p-2 space-y-2">
        {artifacts.map((artifact) => {
          const isHighlighted = highlightedArtifactIds.has(artifact.id);
          return (
          <div
            key={artifact.id}
            onClick={() => handleArtifactClick(artifact)}
            className={`
              bg-white dark:bg-gray-800 border rounded-lg p-3 hover:border-blue-300 dark:hover:border-blue-600 hover:shadow-md transition-all cursor-pointer
              ${isHighlighted
                ? 'border-blue-400 dark:border-blue-500 shadow-lg bg-blue-50 dark:bg-blue-900/20 animate-pulse'
                : 'border-gray-200 dark:border-gray-700'
              }
            `}
            style={isHighlighted ? {
              animation: 'fadeInHighlight 0.5s ease-in-out'
            } : undefined}
          >
          {/* Header */}
          <div className="flex items-start gap-1.5 mb-1">
            <span className="text-lg flex-shrink-0">{getArtifactIcon(artifact.artifact_type)}</span>
            <div className="flex-1 min-w-0">
              <h4 className="font-semibold text-xs text-gray-900 dark:text-gray-100 truncate">{artifact.title}</h4>
              <p className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-1">{artifact.summary}</p>
            </div>
          </div>

          {/* Meta Info */}
          <div className="flex items-center gap-1.5 text-[10px] text-gray-400 dark:text-gray-500 mb-1">
            <span>{artifact.playbook_code}</span>
            <span>•</span>
            <span>{new Date(artifact.created_at).toLocaleDateString('zh-TW')}</span>
            {artifact.intent_id && (
              <>
                <span>•</span>
                <span className="text-blue-500 dark:text-blue-400">{t('sourceIntent') || '來源 Intent'}</span>
              </>
            )}
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-1.5 mt-1">
            {artifact.primary_action_type === 'copy' && (
              <button
                onClick={(e) => handleCopy(artifact, e)}
                className="px-1.5 py-0.5 text-[10px] bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-colors"
              >
                {t('copy') || '複製'}
              </button>
            )}
            {artifact.primary_action_type === 'open_external' && (
              <button
                onClick={(e) => handleOpenExternal(artifact, e)}
                className="px-1.5 py-0.5 text-[10px] bg-green-50 dark:bg-green-900/30 text-green-600 dark:text-green-400 rounded hover:bg-green-100 dark:hover:bg-green-900/40 transition-colors"
              >
                {t('open') || '開啟'}
              </button>
            )}
            {artifact.primary_action_type === 'download' && (
              <button
                onClick={(e) => handleOpenExternal(artifact, e)}
                className="px-1.5 py-0.5 text-[10px] bg-gray-50 dark:bg-gray-800/30 text-gray-600 dark:text-gray-400 rounded hover:bg-gray-100 dark:hover:bg-gray-800/40 transition-colors"
              >
                {t('download') || '下載'}
              </button>
            )}
          </div>
        </div>
        );
        })}
      </div>

      {/* CSS Animation for highlight */}
      <style jsx global>{`
        @keyframes fadeInHighlight {
          0% {
            opacity: 0;
            transform: translateY(-10px) scale(0.98);
            background-color: rgba(59, 130, 246, 0.1);
          }
          50% {
            background-color: rgba(59, 130, 246, 0.2);
          }
          100% {
            opacity: 1;
            transform: translateY(0) scale(1);
            background-color: rgba(239, 246, 255, 1);
          }
        }
      `}</style>
    </>
  );
}

