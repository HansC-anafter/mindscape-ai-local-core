'use client';

import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useConflictHandler } from '@/hooks/useConflictHandler';
import ConflictDialog from '@/components/ConflictDialog';
import { useToast } from '@/components/Toast';

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

interface OutcomeDetailModalProps {
  artifact: Artifact | null;
  isOpen: boolean;
  onClose: () => void;
  workspaceId: string;
  apiUrl: string;
}

const markdownComponents = {
  p: ({ children }: any) => <p className="mb-2 last:mb-0">{children}</p>,
  ul: ({ children }: any) => <ul className="list-disc list-inside mb-2 space-y-1">{children}</ul>,
  ol: ({ children }: any) => <ol className="list-decimal list-inside mb-2 space-y-1">{children}</ol>,
  li: ({ children }: any) => <li className="ml-2">{children}</li>,
  strong: ({ children }: any) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }: any) => <em className="italic">{children}</em>,
  code: ({ children, className }: any) => {
    const isInline = !className;
    return isInline ? (
      <code className="bg-gray-200 px-1 py-0.5 rounded text-xs font-mono">{children}</code>
    ) : (
      <code className="block bg-gray-100 p-2 rounded text-xs font-mono overflow-x-auto">{children}</code>
    );
  },
  pre: ({ children }: any) => <pre className="bg-gray-100 p-2 rounded text-xs font-mono overflow-x-auto mb-2">{children}</pre>,
  h1: ({ children }: any) => <h1 className="text-xl font-bold mb-3">{children}</h1>,
  h2: ({ children }: any) => <h2 className="text-lg font-bold mb-2">{children}</h2>,
  h3: ({ children }: any) => <h3 className="text-base font-bold mb-1">{children}</h3>,
  blockquote: ({ children }: any) => <blockquote className="border-l-4 border-gray-300 pl-2 italic mb-2">{children}</blockquote>,
};

export default function OutcomeDetailModal({
  artifact,
  isOpen,
  onClose,
  workspaceId,
  apiUrl
}: OutcomeDetailModalProps) {
  const [loading, setLoading] = useState(false);
  const { conflictDialog, handleConflict, closeConflictDialog } = useConflictHandler();
  const { showToast, ToastComponent } = useToast();

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

  if (!isOpen || !artifact) return null;

  const handleCopy = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts/${artifact.id}/copy`,
        { method: 'POST' }
      );

      const data = await response.json();

      // Use conflict handler to handle conflicts
      await handleConflict(
        { ...data, status: response.status },
        async () => {
          // Retry with force=true
          const retryResponse = await fetch(
            `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts/${artifact.id}/copy?force=true`,
            { method: 'POST' }
          );
          if (!retryResponse.ok) {
            throw new Error('Failed to copy artifact');
          }
          return await retryResponse.json();
        },
        async (result) => {
          // Success: copy to clipboard
          await navigator.clipboard.writeText(result.content);
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
        },
        async () => {
          // Use new version (if API supports it)
          // For now, just copy the content as-is
          await navigator.clipboard.writeText(data.content);
          showToast({
            message: '已複製到剪貼板（使用新版本）',
            type: 'success',
            duration: 3000
          });
          return data;
        }
      );
    } catch (err) {
      console.error('Failed to copy artifact:', err);
      showToast({
        message: '複製失敗，請重試',
        type: 'error',
        duration: 3000
      });
    } finally {
      setLoading(false);
    }
  };

  const handleOpenExternal = async () => {
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
      // TODO: Show error toast
    }
  };

  const renderDraftContent = () => {
    const content = artifact.content?.content || artifact.content?.content || artifact.summary || '';
    return (
      <div className="prose prose-sm max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {content}
        </ReactMarkdown>
      </div>
    );
  };

  const renderChecklistContent = () => {
    const tasks = artifact.content?.tasks || [];
    return (
      <div className="space-y-2">
        <h3 className="text-lg font-semibold mb-4">任務清單</h3>
        {tasks.length === 0 ? (
          <p className="text-gray-500">尚無任務</p>
        ) : (
          <div className="space-y-2">
            {tasks.map((task: any, index: number) => (
              <div key={task.id || index} className="flex items-start gap-2 p-2 border border-gray-200 rounded">
                <input
                  type="checkbox"
                  checked={task.completed || false}
                  readOnly
                  className="mt-1"
                />
                <div className="flex-1">
                  <div className="font-medium">{task.title}</div>
                  {task.description && (
                    <div className="text-sm text-gray-600 mt-1">{task.description}</div>
                  )}
                  {task.priority && (
                    <span className="inline-block mt-1 px-2 py-0.5 text-xs bg-blue-100 text-blue-700 rounded">
                      {task.priority}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  const renderConfigContent = () => {
    return (
      <div className="space-y-2">
        <pre className="bg-gray-100 p-4 rounded overflow-x-auto text-xs">
          {JSON.stringify(artifact.content, null, 2)}
        </pre>
      </div>
    );
  };

  const renderCanvaContent = () => {
    const canvaUrl = artifact.content?.canva_url || artifact.storage_ref;
    const thumbnailUrl = artifact.content?.thumbnail_url;
    return (
      <div className="space-y-4">
        {thumbnailUrl && (
          <div className="border border-gray-200 rounded-lg overflow-hidden">
            <img src={thumbnailUrl} alt={artifact.title} className="w-full h-auto" />
          </div>
        )}
        {canvaUrl && (
          <button
            onClick={handleOpenExternal}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 transition-colors"
          >
            在 Canva 開啟
          </button>
        )}
      </div>
    );
  };

  const renderAudioContent = () => {
    const audioPath = artifact.content?.audio_file_path || artifact.storage_ref;
    const transcript = artifact.content?.transcript;
    return (
      <div className="space-y-4">
        {audioPath && (
          <div>
            <audio controls className="w-full">
              <source src={audioPath} type="audio/mpeg" />
              <source src={audioPath} type="audio/wav" />
              您的瀏覽器不支援音頻播放。
            </audio>
          </div>
        )}
        {transcript && (
          <div className="mt-4">
            <h3 className="text-lg font-semibold mb-2">文字稿</h3>
            <div className="bg-gray-50 p-4 rounded border border-gray-200">
              <p className="whitespace-pre-wrap text-sm">{transcript}</p>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderContent = () => {
    switch (artifact.artifact_type) {
      case 'draft':
        return renderDraftContent();
      case 'checklist':
        return renderChecklistContent();
      case 'config':
        return renderConfigContent();
      case 'canva':
        return renderCanvaContent();
      case 'audio':
        return renderAudioContent();
      default:
        return (
          <div className="space-y-2">
            <pre className="bg-gray-100 p-4 rounded overflow-x-auto text-xs">
              {JSON.stringify(artifact.content, null, 2)}
            </pre>
          </div>
        );
    }
  };

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

      <div
        className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
        onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl max-w-4xl w-full mx-4 max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
        style={{ marginRight: '320px' }} // Leave space for right sidebar (w-80 = 320px)
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b px-6 py-4 shrink-0">
          <div className="flex-1 min-w-0">
            <h2 className="text-xl font-semibold text-gray-900 truncate">{artifact.title}</h2>
            <div className="flex items-center gap-2 mt-1 text-sm text-gray-500">
              <span>{artifact.playbook_code}</span>
              <span>•</span>
              <span>{new Date(artifact.created_at).toLocaleString('zh-TW')}</span>
            </div>
          </div>
          <div className="flex items-center gap-2 ml-4">
            {artifact.primary_action_type === 'copy' && (
              <button
                onClick={handleCopy}
                disabled={loading}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400 transition-colors"
              >
                {loading ? '複製中...' : '複製全部'}
              </button>
            )}
            {artifact.primary_action_type === 'open_external' && (
              <button
                onClick={handleOpenExternal}
                className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 transition-colors"
              >
                開啟
              </button>
            )}
            {artifact.primary_action_type === 'download' && (
              <button
                onClick={handleOpenExternal}
                className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 transition-colors"
              >
                下載
              </button>
            )}
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 text-2xl leading-none ml-2"
            >
              ×
            </button>
          </div>
        </div>

        {/* Main Content */}
        <div className="flex-1 overflow-y-auto px-6 py-4 min-h-0">
          {renderContent()}
        </div>

        {/* Footer - Metadata */}
        <div className="border-t px-6 py-3 bg-gray-50 shrink-0">
          <div className="space-y-3">
            {/* Basic Metadata */}
            <div className="flex items-center justify-between text-sm text-gray-600">
              <div className="flex items-center gap-4">
                <span>Playbook: {artifact.playbook_code}</span>
                {artifact.execution_id && (
                  <span>執行 ID: {artifact.execution_id.substring(0, 8)}...</span>
                )}
                {artifact.intent_id && (
                  <span className="text-blue-600">來源 Intent</span>
                )}
              </div>
              {artifact.intent_id && (
                <button
                  onClick={() => {
                    // TODO: Navigate to intent or scroll to timeline item
                    console.log('Navigate to intent:', artifact.intent_id);
                  }}
                  className="text-blue-600 hover:text-blue-800 underline"
                >
                  回到該次對話／意圖
                </button>
              )}
            </div>

            {/* Version Info */}
            {artifact.metadata?.version && (
              <div className="flex items-center gap-2 text-sm">
                <span className="text-gray-600">版本:</span>
                <span className="font-mono font-semibold">v{artifact.metadata.version}</span>
                {artifact.metadata.is_latest && (
                  <span className="px-2 py-0.5 text-xs bg-green-100 text-green-700 rounded">
                    最新
                  </span>
                )}
              </div>
            )}

            {/* Storage Path */}
            {artifact.storage_ref && (
              <div className="space-y-1">
                <label className="text-sm font-medium text-gray-700">存儲路徑</label>
                <div className="flex items-center gap-2">
                  <code className="flex-1 bg-white border border-gray-300 rounded px-2 py-1 text-xs font-mono text-gray-800 break-all">
                    {artifact.storage_ref}
                  </code>
                  <button
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(artifact.storage_ref || '');
                        showToast({
                          message: '路徑已複製到剪貼板',
                          type: 'success',
                          duration: 3000
                        });
                      } catch (err) {
                        console.error('Failed to copy path:', err);
                        showToast({
                          message: '複製路徑失敗，請重試',
                          type: 'error',
                          duration: 3000
                        });
                      }
                    }}
                    className="px-3 py-1 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300 transition-colors"
                    title="複製路徑"
                  >
                    複製
                  </button>
                  <button
                    onClick={async () => {
                      try {
                        // Open folder in system file manager
                        const path = artifact.storage_ref || '';
                        if (path) {
                          // Try to extract directory path
                          const dirPath = path.includes('/')
                            ? path.substring(0, path.lastIndexOf('/'))
                            : path;

                          // Call backend API to open folder
                          const response = await fetch(
                            `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts/${artifact.id}/open-folder`,
                            {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({ path: dirPath })
                            }
                          );

                          if (!response.ok) {
                            throw new Error('Failed to open folder');
                          }

                          const result = await response.json();

                          // If backend requires manual opening, show path dialog
                          if (result.requires_manual_open && result.path) {
                            alert(`路徑: ${result.path}\n\n請手動在檔案管理器中開啟此路徑。`);
                          } else {
                            showToast({
                              message: '已開啟資料夾',
                              type: 'success',
                              duration: 3000
                            });
                          }
                        }
                      } catch (err) {
                        console.error('Failed to open folder:', err);
                        // Fallback: Show path in alert
                        const path = artifact.storage_ref || '';
                        const dirPath = path.includes('/')
                          ? path.substring(0, path.lastIndexOf('/'))
                          : path;
                        alert(`路徑: ${dirPath}\n\n請手動在檔案管理器中開啟此路徑。`);
                      }
                    }}
                    className="px-3 py-1 text-xs bg-blue-100 text-blue-700 rounded hover:bg-blue-200 transition-colors"
                    title="開啟所在資料夾"
                  >
                    開啟資料夾
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
    </>
  );
}

