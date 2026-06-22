'use client';

import React, { useState, useEffect } from 'react';
import { useConflictHandler } from '@/hooks/useConflictHandler';
import ConflictDialog from '@/components/ConflictDialog';
import { useToast } from '@/components/Toast';
import { formatLocalDateTime } from '@/lib/time';
import { OutcomeContent } from './outcomeDetailModal/contentRenderers';
import { mergeArtifactDetail } from './outcomeDetailModal/detail';
import type { OutcomeDetailModalProps } from './outcomeDetailModal/types';

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
            <OutcomeContent
              activeArtifact={activeArtifact}
              detailLoading={detailLoading}
              onOpenExternal={handleOpenExternal}
            />
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
