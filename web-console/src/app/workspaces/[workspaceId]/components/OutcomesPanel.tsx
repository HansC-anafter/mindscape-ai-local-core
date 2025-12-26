'use client';

import React, { useState, useEffect, useRef, Suspense } from 'react';
import { useConflictHandler } from '@/hooks/useConflictHandler';
import ConflictDialog from '@/components/ConflictDialog';
import { useToast } from '@/components/Toast';
import { t } from '@/lib/i18n';
import SandboxModalWrapper from '../../components/execution-inspector/SandboxModalWrapper';
import { loadCapabilityUIComponent, artifactsMatchComponent, createLazyCapabilityComponent } from '@/lib/capability-ui-loader';

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
  const [showSandboxModal, setShowSandboxModal] = useState(false);
  const [sandboxId, setSandboxId] = useState<string | null>(null);
  const [sandboxInitialFile, setSandboxInitialFile] = useState<string | null>(null);
  const [executionId, setExecutionId] = useState<string | null>(null);

  // Dynamic capability UI components (boundary: no hardcoded Cloud components)
  const [installedCapabilities, setInstalledCapabilities] = useState<any[]>([]);
  const [capabilityUIComponents, setCapabilityUIComponents] = useState<Map<string, React.ComponentType<any>>>(new Map());
  const [openModalKey, setOpenModalKey] = useState<string | null>(null);

  const loadArtifacts = async () => {
    try {
      setLoading(true);
      setError(null);
      // Use new API parameters for better filtering and content inclusion
      const url = `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts?include_content=true&include_preview=true&limit=100`;
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Failed to load artifacts: ${response.statusText}`);
      }
      const data = await response.json();
      const newArtifacts = data.artifacts || data || [];

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

  // Load installed capabilities and their UI component metadata (boundary: via API, not hardcoded)
  useEffect(() => {
    const loadCapabilities = async () => {
      try {
        const response = await fetch(`${apiUrl}/api/v1/capability-packs/installed-capabilities`);
        if (response.ok) {
          const capabilities = await response.json();
          setInstalledCapabilities(capabilities);
        }
      } catch (err) {
        // Silently fail - capabilities are optional
      }
    };

    loadCapabilities();
  }, [apiUrl]);

  // Load UI components when artifacts change and match component criteria (boundary: lazy loading)
  useEffect(() => {
    const loadMatchingComponents = async () => {
      if (artifacts.length === 0 || installedCapabilities.length === 0) {
        return;
      }

      const componentMap = new Map<string, React.ComponentType<any>>();

      for (const capability of installedCapabilities) {
        if (capability.ui_components && capability.ui_components.length > 0) {
          for (const componentInfo of capability.ui_components) {
            // Check if artifacts match this component's criteria (boundary: generic check)
            if (artifactsMatchComponent(artifacts, componentInfo)) {
              const key = `${capability.code}:${componentInfo.code}`;

              // Check if already loaded to avoid duplicate loading
              setCapabilityUIComponents(prev => {
                if (prev.has(key)) {
                  return prev; // Already loaded, skip
                }
                return prev;
              });

              // Load component asynchronously (with caching in loader)
              loadCapabilityUIComponent(
                capability.code,
                componentInfo.code,
                apiUrl
              ).then(Component => {
                if (Component) {
                  setCapabilityUIComponents(prev => {
                    // Double-check to avoid race conditions
                    if (prev.has(key)) {
                      return prev;
                    }
                    const newMap = new Map(prev);
                    newMap.set(key, Component);
                    return newMap;
                  });
                }
              }).catch(err => {
                console.warn(`Failed to load component ${key}:`, err);
              });
            }
          }
        }
      }
    };

    loadMatchingComponents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifacts.length, installedCapabilities.length, apiUrl]);

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


  // Find matching capability UI components for current artifacts (boundary: generic, no hardcoded logic)
  const matchingComponentKeys: string[] = [];

  for (const capability of installedCapabilities) {
    if (capability.ui_components && capability.ui_components.length > 0) {
      for (const componentInfo of capability.ui_components) {
        const matches = artifactsMatchComponent(artifacts, componentInfo);

        if (matches) {
          const key = `${capability.code}:${componentInfo.code}`;
          if (capabilityUIComponents.has(key)) {
            matchingComponentKeys.push(key);
          }
        }
      }
    }
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

      {/* Dynamic Capability UI Components (boundary: loaded via API, not hardcoded) */}
      {matchingComponentKeys.map((key) => {
        const [capabilityCode, componentCode] = key.split(':');
        const Component = capabilityUIComponents.get(key);
        const capability = installedCapabilities.find(c => c.code === capabilityCode);
        const componentInfo = capability?.ui_components?.find((c: any) => c.code === componentCode);
        const isOpen = openModalKey === key;

        if (!Component || !componentInfo) {
          return null;
        }

        return (
          <div key={key} className="p-2 border-b border-gray-200 dark:border-gray-700">
            <button
              onClick={() => setOpenModalKey(key)}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors text-sm font-medium"
            >
              <span>📱</span>
              <span>{componentInfo.description || `查看 ${componentInfo.code}`}</span>
            </button>
            {isOpen && (
              <Suspense fallback={<div className="p-4 text-center">載入中...</div>}>
                <Component
                  isOpen={isOpen}
                  onClose={() => setOpenModalKey(null)}
                  workspaceId={workspaceId}
                />
              </Suspense>
            )}
          </div>
        );
      })}

      <div className="h-full overflow-y-auto p-2 space-y-2">
        {artifacts.map((artifact) => {
          const isHighlighted = highlightedArtifactIds.has(artifact.id);
          // Extract filePath from multiple possible sources: file_path (API response), storage_ref, or content
          const filePath = (artifact as any).file_path || artifact.storage_ref || (artifact.content && typeof artifact.content === 'object' ? (artifact.content.file_path || artifact.content.file_name) : null) || null;
          const fileName = (artifact.content && typeof artifact.content === 'object' && artifact.content.file_name) ? artifact.content.file_name : artifact.title;
          // Extract execution_id from metadata if not directly available
          const executionId = (artifact as any).execution_id || (artifact.metadata && (artifact.metadata as any).execution_id) || (artifact.metadata && (artifact.metadata as any).navigate_to) || null;
          const createdDate = new Date(artifact.created_at);
          const formattedDate = createdDate.toLocaleString('zh-TW', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
          });


          const handleFileClick = (e: React.MouseEvent) => {
            e.stopPropagation();

            // Extract sandbox ID and relative file path from artifact metadata
            const actualFilePath = (artifact as any).file_path || (artifact.metadata && (artifact.metadata as any).actual_file_path);
            const execId = executionId || (artifact.metadata && (artifact.metadata as any).execution_id);

            // Try to extract sandbox ID from file path
            // Format: /app/data/sandboxes/{workspace_id}/project_repo/{sandbox_id}/current/...
            let extractedSandboxId: string | null = null;
            let relativeFilePath: string | null = null;

            if (actualFilePath) {
              // Extract sandbox ID from path: project_repo/{sandbox_id}/current
              const sandboxMatch = actualFilePath.match(/project_repo\/([^\/]+)\/current\/(.+)$/);
              if (sandboxMatch) {
                extractedSandboxId = sandboxMatch[1];
                relativeFilePath = sandboxMatch[2];
              } else {
                // Fallback: try to extract from other path formats
                const fallbackMatch = actualFilePath.match(/sandboxes\/[^\/]+\/[^\/]+\/([^\/]+)\/current\/(.+)$/);
                if (fallbackMatch) {
                  extractedSandboxId = fallbackMatch[1];
                  relativeFilePath = fallbackMatch[2];
                }
              }
            }

            // Priority: 1. Open SandboxModal if we have sandbox ID and file path, 2. Open artifact detail, 3. Download file
            if (extractedSandboxId && relativeFilePath && execId) {
              // Open SandboxModal with the artifact file
              setSandboxId(extractedSandboxId);
              setSandboxInitialFile(relativeFilePath);
              setExecutionId(execId);
              setShowSandboxModal(true);
            } else if (onArtifactClick) {
              // Open artifact detail dialog
              onArtifactClick(artifact);
            } else if (filePath || actualFilePath) {
              // Last resort: download file
              const fileUrl = `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts/${artifact.id}/file`;
              window.open(fileUrl, '_blank');
            }
          };

          const handleSandboxClick = (e: React.MouseEvent) => {
            e.stopPropagation();
            // Try to find sandbox from execution_id or file path
            if (executionId) {
              // Navigate to execution detail page which should show sandbox
              window.open(`/workspaces/${workspaceId}/executions/${executionId}`, '_blank');
            } else if (filePath) {
              // Extract sandbox ID from file path if available
              // Format: workspace/{workspaceId}/sandboxes/{sandboxId}/...
              const sandboxMatch = filePath.match(/sandboxes\/([^\/]+)/);
              if (sandboxMatch) {
                const sandboxId = sandboxMatch[1];
                window.open(`/workspaces/${workspaceId}/executions?sandbox=${sandboxId}`, '_blank');
              } else {
                // If no sandbox ID, open artifact detail
                handleFileClick(e);
              }
            } else {
              // Fallback: open artifact detail
              handleFileClick(e);
            }
          };

          return (
          <div
            key={artifact.id}
            className={`
              bg-surface-secondary dark:bg-gray-800 border rounded-lg p-2.5 hover:border-accent dark:hover:border-blue-600 hover:shadow-md transition-all
              ${isHighlighted
                ? 'border-accent dark:border-blue-500 shadow-lg bg-accent-10 dark:bg-blue-900/20 animate-pulse'
                : 'border-default dark:border-gray-700'
              }
            `}
            style={isHighlighted ? {
              animation: 'fadeInHighlight 0.5s ease-in-out'
            } : undefined}
          >
          {/* First Row: File Name (Clickable) */}
          <div
            onClick={handleFileClick}
            className="flex items-center gap-2 mb-1 cursor-pointer group"
          >
            <span className="text-base flex-shrink-0">{getArtifactIcon(artifact.artifact_type)}</span>
            <div className="flex-1 min-w-0">
              <div className="font-medium text-sm text-primary dark:text-gray-100 truncate group-hover:text-accent dark:group-hover:text-blue-400 transition-colors">
                {fileName}
              </div>
            </div>
            {artifact.primary_action_type === 'download' && filePath && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleOpenExternal(artifact, e);
                }}
                className="px-2 py-0.5 text-[10px] bg-accent-10 dark:bg-blue-900/30 text-accent dark:text-blue-400 rounded hover:opacity-80 dark:hover:bg-blue-900/40 transition-colors flex-shrink-0"
                title="下載檔案"
              >
                <span>⬇</span>
              </button>
            )}
          </div>

          {/* Second Row: Playbook & Time (Secondary Info) */}
          <div className="flex items-center justify-between text-[10px] text-gray-400 dark:text-gray-500">
            <div className="flex items-center gap-1.5 flex-1 min-w-0">
              <span className="truncate">{artifact.playbook_code}</span>
              <span>•</span>
              <span className="flex-shrink-0">{formattedDate}</span>
            </div>
            {(filePath || executionId) && (
              <button
                onClick={handleSandboxClick}
                className="text-[10px] text-accent dark:text-blue-400 hover:opacity-80 dark:hover:text-blue-300 hover:underline flex-shrink-0 ml-2 px-1 py-0.5 rounded hover:bg-accent-10 dark:hover:bg-blue-900/20 transition-colors"
                title="在 Sandbox 中查看"
              >
                <span className="mr-0.5">📁</span> Sandbox
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

      {/* SandboxModal for viewing artifact files */}
      {showSandboxModal && sandboxId && executionId && (
        <SandboxModalWrapper
          isOpen={showSandboxModal}
          onClose={() => {
            setShowSandboxModal(false);
            setSandboxId(null);
            setSandboxInitialFile(null);
            setExecutionId(null);
          }}
          workspaceId={workspaceId}
          sandboxId={sandboxId}
          executionId={executionId}
          initialFile={sandboxInitialFile || undefined}
        />
      )}

      {/* IG Grid View Modal moved to Cloud - removed from Local-Core */}
    </>
  );
}

