'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { t } from '@/lib/i18n';

export interface ConversationThread {
  id: string;
  workspace_id: string;
  title: string;
  project_id?: string | null;
  pinned_scope?: string | null;
  created_at: string;
  updated_at: string;
  last_message_at: string;
  message_count: number;
  metadata: Record<string, any>;
  is_default: boolean;
}

interface ConversationsListProps {
  workspaceId: string;
  apiUrl: string;
  selectedThreadId: string | null;
  onThreadSelect: (threadId: string | null) => void;
  onCreateThread?: (projectId?: string) => Promise<void>;
}

export default function ConversationsList({
  workspaceId,
  apiUrl,
  selectedThreadId,
  onThreadSelect,
  onCreateThread,
}: ConversationsListProps) {
  const [threads, setThreads] = useState<ConversationThread[]>([]);
  const [loading, setLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadThreads = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/threads`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok) {
        throw new Error(`Failed to load threads: ${response.status}`);
      }

      const data = await response.json();
      setThreads(data || []);
    } catch (err: any) {
      console.error('Failed to load conversations:', err);
      setError(err.message || 'Failed to load conversations');
    } finally {
      setLoading(false);
    }
  }, [workspaceId, apiUrl]);

  // Initial load on mount
  useEffect(() => {
    loadThreads();

    const handleUpdate = () => {
      loadThreads();
    };

    window.addEventListener('workspace-chat-updated', handleUpdate);
    window.addEventListener('workspace-task-updated', handleUpdate);

    return () => {
      window.removeEventListener('workspace-chat-updated', handleUpdate);
      window.removeEventListener('workspace-task-updated', handleUpdate);
    };
  }, [loadThreads]);

  // 🆕 當 threads 載入完成且沒有選擇 thread 時，自動選擇 default thread
  useEffect(() => {
    if (!loading && threads.length > 0 && !selectedThreadId) {
      const defaultThread = threads.find(t => t.is_default);
      if (defaultThread) {
        onThreadSelect(defaultThread.id);
      } else if (threads.length > 0) {
        // 如果沒有 default thread，選擇第一個
        onThreadSelect(threads[0].id);
      }
    }
  }, [loading, threads, selectedThreadId, onThreadSelect]);

  const handleCreateThread = useCallback(async (projectId?: string) => {
    if (isCreating) return;

    try {
      setIsCreating(true);
      setError(null);

      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/threads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to create thread: ${response.status}`);
      }

      const newThread = await response.json();

      // Reload threads list
      await loadThreads();

      // Switch to new thread
      onThreadSelect(newThread.id);

      // Dispatch event for auto-focus (optional)
      window.dispatchEvent(new CustomEvent('thread-created', {
        detail: { threadId: newThread.id }
      }));

      // Call optional callback
      if (onCreateThread) {
        await onCreateThread(projectId);
      }
    } catch (err: any) {
      console.error('Failed to create thread:', err);
      setError(err.message || 'Failed to create thread');
    } finally {
      setIsCreating(false);
    }
  }, [workspaceId, apiUrl, isCreating, loadThreads, onThreadSelect, onCreateThread]);

  const parseApiDate = (dateString: string) => {
    // If the backend returns a naive ISO string (no timezone), treat it as UTC.
    // If it already includes timezone ("Z" or "+hh:mm"), let Date parse it as-is.
    const s = (dateString || '').trim();
    if (!s) return new Date(NaN);
    const hasTimezone = /([zZ]|[+\-]\d{2}:\d{2})$/.test(s);
    return new Date(hasTimezone ? s : `${s}Z`);
  };

  const formatDate = (dateString: string) => {
    const date = parseApiDate(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return t('justNow' as any) || '剛剛';
    if (diffMins < 60) return (t('minutesAgo', { count: String(diffMins) }) as string) || `${diffMins} 分鐘前`;
    if (diffHours < 24) return (t('hoursAgo', { count: String(diffHours) }) as string) || `${diffHours} 小時前`;
    if (diffDays < 7) return `${diffDays} 天前`;
    return date.toLocaleDateString('zh-TW', { month: 'short', day: 'numeric' });
  };

  return (
    <div className="flex flex-col h-full">
      {/* 新增對話按鈕 - 固定在頂部 */}
      <div className="flex-shrink-0 p-2 border-b dark:border-gray-700">
        <button
          onClick={() => handleCreateThread()}
          disabled={isCreating}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium
                     bg-accent dark:bg-blue-600 text-white rounded-lg
                     hover:bg-accent/90 dark:hover:bg-blue-700
                     disabled:opacity-50 disabled:cursor-not-allowed
                     transition-colors"
        >
          {isCreating ? (
            <>
              <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              <span>創建中...</span>
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              <span>新建對話</span>
            </>
          )}
        </button>
      </div>

      {/* 錯誤提示 */}
      {error && (
        <div className="flex-shrink-0 p-2 border-b dark:border-gray-700">
          <div className="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 px-2 py-1 rounded">
            {error}
          </div>
        </div>
      )}

      {/* 對話列表 - 可滾動 */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center p-4">
            <div className="text-sm text-gray-500 dark:text-gray-400">載入中...</div>
          </div>
        ) : threads.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-4 text-center">
            <div className="text-2xl mb-2">💬</div>
            <div className="text-sm text-gray-500 dark:text-gray-400">
              還沒有對話
            </div>
            <div className="text-xs text-gray-400 dark:text-gray-500 mt-1">
              點擊上方按鈕開始新對話
            </div>
          </div>
        ) : (
          <div className="p-2 space-y-1">
            {threads.map(thread => (
              <button
                key={thread.id}
                onClick={() => onThreadSelect(thread.id)}
                className={`w-full text-left px-3 py-2 text-sm rounded-lg transition-colors ${selectedThreadId === thread.id
                    ? 'bg-accent-10 dark:bg-blue-900/30 text-accent dark:text-blue-300'
                    : 'hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300'
                  }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate">
                      {thread.is_default && (
                        <span className="text-xs text-gray-500 dark:text-gray-400 mr-1">[預設]</span>
                      )}
                      {thread.title === '新對話'
                        ? `新對話 ${parseApiDate(thread.created_at).toLocaleString('zh-TW', {
                          year: 'numeric',
                          month: '2-digit',
                          day: '2-digit',
                          hour: '2-digit',
                          minute: '2-digit',
                          hour12: false,
                        })}`
                        : thread.title}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                      {formatDate(thread.last_message_at)} • {thread.message_count} 則訊息
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
