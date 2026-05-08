'use client';

import React, { useState, useEffect } from 'react';
import Image from 'next/image';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useConflictHandler } from '@/hooks/useConflictHandler';
import ConflictDialog from '@/components/ConflictDialog';
import { useToast } from '@/components/Toast';
import { formatLocalDateTime } from '@/lib/time';

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
      <code className="bg-gray-200 dark:bg-gray-700 px-1 py-0.5 rounded text-xs font-mono">{children}</code>
    ) : (
      <code className="block bg-gray-100 dark:bg-gray-800 p-2 rounded text-xs font-mono overflow-x-auto">{children}</code>
    );
  },
  pre: ({ children }: any) => <pre className="bg-gray-100 dark:bg-gray-800 p-2 rounded text-xs font-mono overflow-x-auto mb-2">{children}</pre>,
  h1: ({ children }: any) => <h1 className="text-xl font-bold mb-3">{children}</h1>,
  h2: ({ children }: any) => <h2 className="text-lg font-bold mb-2">{children}</h2>,
  h3: ({ children }: any) => <h3 className="text-base font-bold mb-1">{children}</h3>,
  blockquote: ({ children }: any) => <blockquote className="border-l-4 border-gray-300 dark:border-gray-600 pl-2 italic mb-2">{children}</blockquote>,
};

const mergeArtifactDetail = (base: Artifact, detail: any): Artifact => ({
  ...base,
  ...detail,
  summary: detail.summary ?? detail.description ?? base.summary,
  storage_ref: detail.storage_ref ?? detail.file_path ?? base.storage_ref,
  primary_action_type: detail.primary_action_type ?? base.primary_action_type,
  metadata: detail.metadata ?? base.metadata ?? {},
  content: detail.content ?? base.content,
});

export default function OutcomeDetailModal({
  artifact,
  isOpen,
  onClose,
  workspaceId,
  apiUrl
}: OutcomeDetailModalProps) {
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailArtifact, setDetailArtifact] = useState<Artifact | null>(null);
  const { conflictDialog, handleConflict, closeConflictDialog } = useConflictHandler();
  const { showToast, ToastComponent } = useToast();

  useEffect(() => {
    if (!isOpen || !artifact?.id) {
      setDetailArtifact(null);
      return;
    }

    let cancelled = false;
    setDetailLoading(!artifact.content);

    const loadArtifactDetail = async () => {
      try {
        const response = await fetch(
          `${apiUrl}/api/v1/artifacts/${artifact.id}?include_content=true&include_preview=true`
        );
        if (!response.ok) {
          throw new Error(`Failed to load outcome detail: ${response.statusText}`);
        }
        const detail = await response.json();
        if (!cancelled) {
          setDetailArtifact(mergeArtifactDetail(artifact, detail));
        }
      } catch (err) {
        console.error('Failed to load outcome detail:', err);
        if (!cancelled) {
          setDetailArtifact(artifact);
        }
      } finally {
        if (!cancelled) {
          setDetailLoading(false);
        }
      }
    };

    loadArtifactDetail();
    return () => {
      cancelled = true;
    };
  }, [apiUrl, artifact, isOpen]);

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
  const activeArtifact = detailArtifact || artifact;

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
            message: 'Copied to clipboard',
            type: 'success',
            duration: 3000
          });
        },
        (err) => {
          console.error('Failed to copy artifact:', err);
          showToast({
            message: 'Copy failed. Please try again.',
            type: 'error',
            duration: 3000
          });
        },
        async () => {
          // Use new version (if API supports it)
          // For now, just copy the content as-is
          await navigator.clipboard.writeText(data.content);
          showToast({
            message: 'Copied to clipboard using the new version',
            type: 'success',
            duration: 3000
          });
          return data;
        }
      );
    } catch (err) {
      console.error('Failed to copy artifact:', err);
      showToast({
        message: 'Copy failed. Please try again.',
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
      showToast({
        message: 'Failed to open external URL.',
        type: 'error',
        duration: 3000
      });
    }
  };

  const renderDraftContent = () => {
    const content = activeArtifact.content?.content || activeArtifact.summary || '';
    return (
      <div className="prose prose-sm max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {content}
        </ReactMarkdown>
      </div>
    );
  };

  const renderChecklistContent = () => {
    const tasks = activeArtifact.content?.tasks || [];
    return (
      <div className="space-y-2">
        <h3 className="text-lg font-semibold mb-4 dark:text-gray-100">Task List</h3>
        {tasks.length === 0 ? (
          <p className="text-gray-500 dark:text-gray-400">No tasks yet</p>
        ) : (
          <div className="space-y-2">
            {tasks.map((task: any, index: number) => (
              <div key={task.id || index} className="flex items-start gap-2 p-2 border border-gray-200 dark:border-gray-700 rounded bg-white dark:bg-gray-800">
                <input
                  type="checkbox"
                  checked={task.completed || false}
                  readOnly
                  className="mt-1"
                />
                <div className="flex-1">
                  <div className="font-medium dark:text-gray-100">{task.title}</div>
                  {task.description && (
                    <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">{task.description}</div>
                  )}
                  {task.priority && (
                    <span className="inline-block mt-1 px-2 py-0.5 text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded">
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
        <pre className="bg-gray-100 dark:bg-gray-800 p-4 rounded overflow-x-auto text-xs text-gray-900 dark:text-gray-100">
          {JSON.stringify(activeArtifact.content, null, 2)}
        </pre>
      </div>
    );
  };

  const renderCanvaContent = () => {
    const canvaUrl = activeArtifact.content?.canva_url || activeArtifact.storage_ref;
    const thumbnailUrl = activeArtifact.content?.thumbnail_url;
    return (
      <div className="space-y-4">
        {thumbnailUrl && (
          <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
            <Image
              src={thumbnailUrl}
              alt={activeArtifact.title}
              width={960}
              height={540}
              className="w-full h-auto"
              unoptimized
            />
          </div>
        )}
        {canvaUrl && (
          <button
            onClick={handleOpenExternal}
            className="px-4 py-2 bg-green-600 dark:bg-green-700 text-white rounded hover:bg-green-700 dark:hover:bg-green-600 transition-colors"
          >
            Open in Canva
          </button>
        )}
      </div>
    );
  };

  const renderAudioContent = () => {
    const audioPath = activeArtifact.content?.audio_file_path || activeArtifact.storage_ref;
    const transcript = activeArtifact.content?.transcript;
    return (
      <div className="space-y-4">
        {audioPath && (
          <div>
            <audio controls className="w-full">
              <source src={audioPath} type="audio/mpeg" />
              <source src={audioPath} type="audio/wav" />
              Your browser does not support audio playback.
            </audio>
          </div>
        )}
        {transcript && (
          <div className="mt-4">
            <h3 className="text-lg font-semibold mb-2 dark:text-gray-100">Transcript</h3>
            <div className="bg-gray-50 dark:bg-gray-800 p-4 rounded border border-gray-200 dark:border-gray-700">
              <p className="whitespace-pre-wrap text-sm dark:text-gray-300">{transcript}</p>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderContent = () => {
    if (detailLoading && !activeArtifact.content) {
      return <div className="text-sm text-gray-500 dark:text-gray-400">Loading outcome content...</div>;
    }

    switch (activeArtifact.artifact_type) {
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
            <pre className="bg-gray-100 dark:bg-gray-800 p-4 rounded overflow-x-auto text-xs text-gray-900 dark:text-gray-100">
              {JSON.stringify(activeArtifact.content, null, 2)}
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
          className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-4xl w-full mx-4 max-h-[90vh] flex flex-col"
          onClick={(e) => e.stopPropagation()}
          style={{ marginRight: '320px' }} // Leave space for right sidebar (w-80 = 320px)
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b dark:border-gray-700 px-6 py-4 shrink-0">
            <div className="flex-1 min-w-0">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 truncate">{activeArtifact.title}</h2>
              <div className="flex items-center gap-2 mt-1 text-sm text-gray-500 dark:text-gray-400">
                <span>{activeArtifact.playbook_code}</span>
                <span>-</span>
                <span>{formatLocalDateTime(activeArtifact.created_at)}</span>
              </div>
            </div>
            <div className="flex items-center gap-2 ml-4">
              {activeArtifact.primary_action_type === 'copy' && (
                <button
                  onClick={handleCopy}
                  disabled={loading}
                  className="px-4 py-2 bg-blue-600 dark:bg-blue-700 text-white rounded hover:bg-blue-700 dark:hover:bg-blue-600 disabled:bg-gray-400 dark:disabled:bg-gray-600 transition-colors"
                >
                  {loading ? 'Copying...' : 'Copy All'}
                </button>
              )}
              {activeArtifact.primary_action_type === 'open_external' && (
                <button
                  onClick={handleOpenExternal}
                  className="px-4 py-2 bg-green-600 dark:bg-green-700 text-white rounded hover:bg-green-700 dark:hover:bg-green-600 transition-colors"
                >
                  Open
                </button>
              )}
              {activeArtifact.primary_action_type === 'download' && (
                <button
                  onClick={handleOpenExternal}
                  className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded hover:bg-gray-700 dark:hover:bg-gray-600 transition-colors"
                >
                  Download
                </button>
              )}
              <button
                onClick={onClose}
                className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 text-2xl leading-none ml-2"
              >
                Close
              </button>
            </div>
          </div>

          {/* Main Content */}
          <div className="flex-1 overflow-y-auto px-6 py-4 min-h-0">
            {renderContent()}
          </div>

          <div className="border-t dark:border-gray-700 px-6 py-3 bg-gray-50 dark:bg-gray-800 shrink-0">
            <div className="space-y-3">
              <div className="flex items-center justify-between text-sm text-gray-600 dark:text-gray-400">
                <div className="flex items-center gap-4">
                  <span>Playbook: {activeArtifact.playbook_code}</span>
                  {activeArtifact.execution_id && (
                    <span>Execution ID: {activeArtifact.execution_id.substring(0, 8)}...</span>
                  )}
                  {activeArtifact.intent_id && (
                    <span className="text-blue-600 dark:text-blue-400">Source Intent</span>
                  )}
                </div>
              </div>

              {/* Version Info */}
              {activeArtifact.metadata?.version && (
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-gray-600 dark:text-gray-400">Version:</span>
                  <span className="font-mono font-semibold dark:text-gray-100">v{activeArtifact.metadata.version}</span>
                  {activeArtifact.metadata.is_latest && (
                    <span className="px-2 py-0.5 text-xs bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded">
                      Latest
                    </span>
                  )}
                </div>
              )}

              {/* Storage Path */}
              {activeArtifact.storage_ref && (
                <div className="space-y-1">
                  <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Storage Path</label>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 bg-white dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-xs font-mono text-gray-800 dark:text-gray-200 break-all">
                      {activeArtifact.storage_ref}
                    </code>
                    <button
                      onClick={async () => {
                        try {
                          await navigator.clipboard.writeText(activeArtifact.storage_ref || '');
                          showToast({
                            message: 'Path copied to clipboard',
                            type: 'success',
                            duration: 3000
                          });
                        } catch (err) {
                          console.error('Failed to copy path:', err);
                          showToast({
                            message: 'Failed to copy path. Please try again.',
                            type: 'error',
                            duration: 3000
                          });
                        }
                      }}
                      className="px-3 py-1 text-xs bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
                      title="Copy Path"
                    >
                      Copy
                    </button>
                    <button
                      onClick={async () => {
                        try {
                          // Open folder in system file manager
                          const path = activeArtifact.storage_ref || '';
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
                              alert(`Path: ${result.path}\n\nOpen this path manually in your file manager.`);
                            } else {
                              showToast({
                                message: 'Folder opened',
                                type: 'success',
                                duration: 3000
                              });
                            }
                          }
                        } catch (err) {
                          console.error('Failed to open folder:', err);
                          // Fallback: Show path in alert
                          const path = activeArtifact.storage_ref || '';
                          const dirPath = path.includes('/')
                            ? path.substring(0, path.lastIndexOf('/'))
                            : path;
                          alert(`Path: ${dirPath}\n\nOpen this path manually in your file manager.`);
                        }
                      }}
                      className="px-3 py-1 text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded hover:bg-blue-200 dark:hover:bg-blue-900/40 transition-colors"
                      title="Open Containing Folder"
                    >
                      Open Folder
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
