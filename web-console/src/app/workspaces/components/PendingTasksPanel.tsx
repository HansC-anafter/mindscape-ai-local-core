'use client';

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useT } from '@/lib/i18n';
import HelpIcon from '@/components/HelpIcon';
import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { getPlaybookMetadata } from '@/lib/i18n/locales/playbooks';
import { playbookMetadataZhTW } from '@/lib/i18n/locales/playbooks/metadata/zh-TW';
import { getApiBaseUrl } from '../../../lib/api-url';

// Component for displaying and editing AI-inferred intent label
function PlaybookIntentSubtitle({
  workspaceId,
  apiUrl,
  messageId
}: {
  workspaceId: string;
  apiUrl: string;
  messageId: string;
}) {
  const t = useT();
  const [intentTag, setIntentTag] = useState<any>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editedLabel, setEditedLabel] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Fetch candidate intent tag for this message
    const fetchIntentTag = async () => {
      try {
        setLoading(true);
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/intent-tags/candidates?message_id=${messageId}&limit=1`
        );
        if (response.ok) {
          const data = await response.json();
          if (data.intent_tags && data.intent_tags.length > 0) {
            setIntentTag(data.intent_tags[0]);
            setEditedLabel(data.intent_tags[0].title);
          }
        }
      } catch (err) {
        console.error('Failed to fetch intent tag:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchIntentTag();
  }, [workspaceId, apiUrl, messageId]);

  const handleSaveEdit = async () => {
    if (!intentTag || !editedLabel.trim()) return;

    try {
      // Update intent tag label
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/intent-tags/${intentTag.id}/label`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ label: editedLabel.trim() })
        }
      );
      if (response.ok) {
        setIsEditing(false);
        setIntentTag({ ...intentTag, title: editedLabel.trim() });
        // Trigger refresh
        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
      } else {
        const error = await response.json();
        console.error('Failed to update intent tag label:', error);
        alert(`Failed to update label: ${error.detail || t('unknownError' as any)}`);
      }
    } catch (err: any) {
      console.error('Failed to update intent tag label:', err);
      alert(`Failed to update label: ${err.message || t('unknownError' as any)}`);
    }
  };

  if (loading || !intentTag) return null;

  return (
    <div className="text-[10px] text-gray-500 dark:text-gray-400 mb-1.5 flex items-center gap-1.5">
      <span>{t('intentBasedOnAISuggestion' as any)}</span>
      {isEditing ? (
        <div className="flex items-center gap-1">
          <input
            type="text"
            value={editedLabel}
            onChange={(e) => setEditedLabel(e.target.value)}
            className="text-[10px] px-1 py-0.5 border border-gray-300 dark:border-gray-600 rounded flex-1 min-w-0 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:focus:ring-blue-400 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                handleSaveEdit();
              } else if (e.key === 'Escape') {
                setIsEditing(false);
                setEditedLabel(intentTag.title);
              }
            }}
            autoFocus
          />
          <button
            onClick={handleSaveEdit}
            className="text-[10px] text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300"
          >
            {t('save' as any)}
          </button>
          <button
            onClick={() => {
              setIsEditing(false);
              setEditedLabel(intentTag.title);
            }}
            className="text-[10px] text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
          >
            {t('cancel' as any)}
          </button>
        </div>
      ) : (
        <>
          <span className="font-medium">{intentTag.title}</span>
          <button
            onClick={() => setIsEditing(true)}
            className="text-[10px] text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
            title={t('editIntentLabel' as any)}
          >
            ✎
          </button>
        </>
      )}
    </div>
  );
}

// Laser scan effect styles
const laserScanStyle = `
  @keyframes laser-scan {
    0% {
      transform: translateX(-100%);
    }
    100% {
      transform: translateX(300%);
    }
  }

  .laser-scan-text {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: rgb(37, 99, 235);
    overflow: hidden;
    line-height: 1;
  }

  .laser-scan-text::after {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    width: 30%;
    height: 100%;
    background: linear-gradient(
      90deg,
      transparent,
      rgba(255, 255, 255, 0.8),
      rgba(255, 255, 255, 1),
      rgba(255, 255, 255, 0.8),
      transparent
    );
    animation: laser-scan 2.5s linear infinite;
    pointer-events: none;
    mix-blend-mode: overlay;
  }
`;

interface Task {
  id: string;
  workspace_id: string;
  pack_id?: string;
  playbook_id?: string;
  task_type?: string;
  status: 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED';
  title?: string;
  summary?: string;
  message_id?: string;
  created_at: string;
  updated_at?: string;
  completed_at?: string;
  data?: any;
  params?: any;
  result?: any;
  artifact_creation_failed?: boolean;
  artifact_warning?: any;
}

interface PendingTasksPanelProps {
  workspaceId: string;
  apiUrl?: string;
  onViewArtifact?: (artifact: any) => void;
  onSwitchToOutcomes?: () => void;
  workspace?: {
    playbook_auto_execution_config?: Record<string, {
      confidence_threshold?: number;
      auto_execute?: boolean;
    }>;
  };
  onTaskCountChange?: (count: number) => void;
}

export default function PendingTasksPanel({
  workspaceId,
  apiUrl = getApiBaseUrl(),
  onViewArtifact,
  onSwitchToOutcomes,
  workspace: workspaceProp,
  onTaskCountChange,
}: PendingTasksPanelProps) {
  const t = useT();

  // Use context data if available (when inside WorkspaceDataProvider)
  const contextData = useWorkspaceDataOptional();

  const [localTasks, setLocalTasks] = useState<Task[]>([]);
  const [backgroundTasks, setBackgroundTasks] = useState<Task[]>([]);
  const [backgroundRoutines, setBackgroundRoutines] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [artifactMap, setArtifactMap] = useState<Record<string, any>>({});
  const [executingTaskIds, setExecutingTaskIds] = useState<Set<string>>(new Set());
  const [taskStatusMessages, setTaskStatusMessages] = useState<Record<string, string>>({});
  const [rejectedTasks, setRejectedTasks] = useState<Record<string, { timestamp: number; canRestore: boolean }>>({});
  const [showRejectDialog, setShowRejectDialog] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState<string>('');
  const [rejectComment, setRejectComment] = useState<string>('');
  const loadingRef = React.useRef(false);

  // Use context data if available, otherwise use local state or props
  const allTasksFromContext = contextData?.tasks || [];
  const workspace = contextData?.workspace || workspaceProp;

  // Process and filter tasks (same logic for both context and local data)
  const processedTasks = useMemo(() => {
    const allTasks = contextData ? allTasksFromContext : localTasks;

    // Debug: Log task sources
    console.log('[PendingTasksPanel] processedTasks - contextData:', !!contextData, 'allTasksFromContext:', allTasksFromContext.length, 'localTasks:', localTasks.length, 'allTasks:', allTasks?.length || 0);

    if (!allTasks || allTasks.length === 0) {
      console.log('[PendingTasksPanel] No tasks available');
      return [];
    }

    // Separate background tasks from foreground tasks
    const backgroundPlaybookCodes = ['habit_learning'];

    // Filter background tasks
    const backgroundTasks = allTasks.filter((task: any) => {
      const playbookCode = task.pack_id || task.playbook_id || '';
      const isBackground = backgroundPlaybookCodes.includes(playbookCode.toLowerCase()) ||
        task.result?.llm_analysis?.is_background ||
        task.data?.execution_context?.run_mode === 'background';
      return isBackground;
    });

    // Filter foreground tasks
    const foregroundTasks = allTasks.filter((task: any) => {
      const playbookCode = task.pack_id || task.playbook_id || '';
      const isBackground = backgroundPlaybookCodes.includes(playbookCode.toLowerCase()) ||
        task.result?.llm_analysis?.is_background ||
        task.data?.execution_context?.run_mode === 'background';
      return !isBackground;
    });

    // Filter out auto-executed intent_extraction tasks and system playbooks
    // These are already executed automatically and should not appear in pending decisions
    const tasksNeedingDecision = foregroundTasks.filter((task: any) => {
      // Exclude auto_intent_extraction tasks (already auto-executed)
      if (task.task_type === 'auto_intent_extraction') {
        console.log('[PendingTasksPanel] Filtered out auto_intent_extraction task:', task.id);
        return false;
      }
      // Exclude intent_extraction tasks that are already auto-executed (status SUCCEEDED with auto_executed flag)
      if ((task.pack_id === 'intent_extraction' || task.playbook_id === 'intent_extraction') &&
        task.status?.toUpperCase() === 'SUCCEEDED' &&
        (task.params?.auto_executed || task.result?.auto_executed)) {
        console.log('[PendingTasksPanel] Filtered out auto-executed intent_extraction task:', task.id);
        return false;
      }
      // Exclude system playbooks (e.g., execution_status_query) - these are internal system tools
      const playbookCode = task.pack_id || task.playbook_id || '';
      const systemPlaybookCodes = ['execution_status_query'];
      if (systemPlaybookCodes.includes(playbookCode)) {
        console.log('[PendingTasksPanel] Filtered out system playbook:', playbookCode, task.id);
        return false;
      }
      return true;
    });

    // Debug: Log tasks needing decision
    console.log('[PendingTasksPanel] Tasks needing decision:', tasksNeedingDecision.length, tasksNeedingDecision.map((t: any) => ({
      id: t.id,
      pack_id: t.pack_id,
      task_type: t.task_type,
      status: t.status
    })));

    // Only show PENDING tasks in pending panel
    const activeTasks = tasksNeedingDecision.filter(
      (task: any) => task.status?.toUpperCase() === 'PENDING'
    );

    // Debug: Log filtered tasks
    if (activeTasks.length > 0) {
      console.log('[PendingTasksPanel] Active tasks after filtering:', activeTasks.map((t: any) => ({
        id: t.id,
        pack_id: t.pack_id,
        task_type: t.task_type,
        status: t.status
      })));
    }

    // Also include recently completed foreground tasks (within last 5 minutes)
    // Exclude auto-executed intent_extraction tasks
    const recentCompletedTasks = tasksNeedingDecision.filter((task: any) => {
      if (task.status?.toUpperCase() !== 'SUCCEEDED') return false;
      const completedAt = task.completed_at || task.updated_at || task.created_at;
      if (!completedAt) return false;
      // Backend returns UTC time without timezone indicator, parse as UTC
      const completedTimeStr = completedAt.includes('Z') || completedAt.includes('+') || completedAt.includes('-', 11)
        ? completedAt
        : completedAt + 'Z';
      const completedTime = new Date(completedTimeStr).getTime();
      const fiveMinutesAgo = Date.now() - 5 * 60 * 1000;
      return completedTime > fiveMinutesAgo;
    });

    return [...activeTasks, ...recentCompletedTasks];
  }, [contextData ? allTasksFromContext : localTasks]);

  const tasks = processedTasks;

  // Notify parent component of task count changes
  useEffect(() => {
    if (onTaskCountChange) {
      onTaskCountChange(tasks.length);
    }
  }, [tasks.length, onTaskCountChange]);

  useEffect(() => {
    // Only load tasks if not using context
    if (!contextData) {
      loadTasks();
    }

    // Event handling is done by context when available
    if (contextData) {
      return; // Context handles event-based refresh
    }

    // Fallback: local event handling when not using context
    let debounceTimer: NodeJS.Timeout | null = null;
    let isPending = false;

    const handleChatUpdate = () => {
      console.log('[PendingTasksPanel] workspace-chat-updated event received');
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }
      debounceTimer = setTimeout(() => {
        if (!isPending && !loadingRef.current) {
          console.log('[PendingTasksPanel] Debounce triggered, loading tasks...');
          isPending = true;
          loadTasks().finally(() => {
            isPending = false;
          });
        } else {
          console.log('[PendingTasksPanel] Skip: isPending=', isPending, 'loading=', loadingRef.current);
        }
      }, 2000);
    };

    const handleTaskUpdate = () => {
      console.log('[PendingTasksPanel] workspace-task-updated event received');
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }
      debounceTimer = setTimeout(() => {
        if (!isPending && !loadingRef.current) {
          console.log('[PendingTasksPanel] Debounce triggered, loading tasks...');
          isPending = true;
          loadTasks().finally(() => {
            isPending = false;
          });
        } else {
          console.log('[PendingTasksPanel] Skip: isPending=', isPending, 'loading=', loadingRef.current);
        }
      }, 2000);
    };

    window.addEventListener('workspace-chat-updated', handleChatUpdate);
    window.addEventListener('workspace-task-updated', handleTaskUpdate);

    return () => {
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }
      window.removeEventListener('workspace-chat-updated', handleChatUpdate);
      window.removeEventListener('workspace-task-updated', handleTaskUpdate);
    };
  }, [workspaceId, contextData]);

  const loadTasks = async () => {
    // Skip if using context data
    if (contextData) return;

    // Skip if already loading to prevent overlapping requests
    if (loadingRef.current) {
      console.log('[PendingTasksPanel] loadTasks: Already loading, skipping...');
      return;
    }

    try {
      console.log('[PendingTasksPanel] loadTasks: Starting...');
      loadingRef.current = true;
      setLoading(true);
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/tasks?limit=20&include_completed=true`
      );
      if (response.ok) {
        const data = await response.json();
        const allTasks = data.tasks || [];

        // Separate background tasks from foreground tasks
        const backgroundPlaybookCodes = ['habit_learning']; // Add more background playbooks as needed

        // Filter background tasks (these should be managed separately, not shown as pending tasks)
        const backgroundTasks = allTasks.filter((task: Task) => {
          const playbookCode = task.pack_id || task.playbook_id || '';
          const isBackground = backgroundPlaybookCodes.includes(playbookCode.toLowerCase()) ||
            task.result?.llm_analysis?.is_background ||
            task.data?.execution_context?.run_mode === 'background';
          return isBackground;
        });

        // Filter foreground tasks for PENDING tasks only (RUNNING tasks should not appear in pending panel)
        const foregroundTasks = allTasks.filter((task: Task) => {
          const playbookCode = task.pack_id || task.playbook_id || '';
          const isBackground = backgroundPlaybookCodes.includes(playbookCode.toLowerCase()) ||
            task.result?.llm_analysis?.is_background ||
            task.data?.execution_context?.run_mode === 'background';
          return !isBackground;
        });

        // Filter out auto-executed intent_extraction tasks
        // These are already executed automatically and should not appear in pending decisions
        const tasksNeedingDecision = foregroundTasks.filter((task: Task) => {
          // Exclude auto_intent_extraction tasks (already auto-executed)
          if (task.task_type === 'auto_intent_extraction') {
            return false;
          }
          // Exclude intent_extraction tasks that are already auto-executed (status SUCCEEDED with auto_executed flag)
          if ((task.pack_id === 'intent_extraction' || task.playbook_id === 'intent_extraction') &&
            task.status?.toUpperCase() === 'SUCCEEDED' &&
            (task.params?.auto_executed || (task.result as any)?.auto_executed)) {
            return false;
          }
          return true;
        });

        // Only show PENDING tasks in pending panel (RUNNING tasks should appear in execution console, not here)
        const activeTasks = tasksNeedingDecision.filter(
          (task: Task) => task.status?.toUpperCase() === 'PENDING'
        );

        // Debug: Log filtered tasks
        if (activeTasks.length > 0) {
          console.log('[PendingTasksPanel] Active tasks after filtering (loadTasks):', activeTasks.map((t: Task) => ({
            id: t.id,
            pack_id: t.pack_id,
            task_type: t.task_type,
            status: t.status
          })));
        }

        // Also include recently completed foreground tasks (within last 5 minutes) that have artifacts
        // Exclude auto-executed intent_extraction tasks
        const recentCompletedTasks = tasksNeedingDecision.filter((task: Task) => {
          if (task.status?.toUpperCase() !== 'SUCCEEDED') return false;
          const completedAt = task.completed_at || task.updated_at || task.created_at;
          if (!completedAt) return false;
          // Backend returns UTC time without timezone indicator, parse as UTC
          const completedTimeStr = completedAt.includes('Z') || completedAt.includes('+') || completedAt.includes('-', 11)
            ? completedAt
            : completedAt + 'Z';
          const completedTime = new Date(completedTimeStr).getTime();
          const fiveMinutesAgo = Date.now() - 5 * 60 * 1000;
          return completedTime > fiveMinutesAgo;
        });

        setLocalTasks([...activeTasks, ...recentCompletedTasks]);

        // Store background tasks separately for rendering (only PENDING ones for suggestion)
        const pendingBackgroundTasks = backgroundTasks.filter(
          (task: Task) => task.status?.toUpperCase() === 'PENDING'
        );
        setBackgroundTasks(pendingBackgroundTasks);

        // Load background routines from API
        try {
          const routinesResponse = await fetch(
            `${apiUrl}/api/v1/workspaces/${workspaceId}/background-routines`
          );
          if (routinesResponse.ok) {
            const routinesData = await routinesResponse.json();
            setBackgroundRoutines(routinesData.routines || []);
          }
        } catch (err) {
          console.error('Failed to load background routines:', err);
        }

        // Load artifacts for completed tasks - lazy load on demand instead of batch loading
        // This significantly reduces initial API calls
        // Artifacts will be loaded when user clicks "View Artifact" button
        // Only pre-load artifacts if explicitly needed for display (currently not needed)
      } else if (response.status === 429) {
        // Rate limited - skip this update, will retry on next interval
        console.warn('Rate limited when loading tasks, will retry later');
      }
    } catch (err) {
      console.error('[PendingTasksPanel] Failed to load tasks:', err);
    } finally {
      loadingRef.current = false;
      setLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    const statusUpper = status?.toUpperCase();
    switch (statusUpper) {
      case 'RUNNING':
        return 'bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 border-blue-300 dark:border-blue-700';
      case 'PENDING':
        return 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300 border-yellow-300 dark:border-yellow-700';
      case 'SUCCEEDED':
        return 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 border-green-300 dark:border-green-700';
      case 'FAILED':
        return 'bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300 border-red-300 dark:border-red-700';
      default:
        return 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-300 border-gray-300 dark:border-gray-600';
    }
  };

  const getStatusIcon = (status: string) => {
    const statusUpper = status?.toUpperCase();
    switch (statusUpper) {
      case 'RUNNING':
        return '';
      case 'PENDING':
        return '';
      case 'SUCCEEDED':
        return '';
      case 'FAILED':
        return '';
      default:
        return '';
    }
  };

  const formatTime = (timestamp: string) => {
    try {
      // Backend returns UTC time without timezone indicator, parse as UTC
      const timeStr = timestamp.includes('Z') || timestamp.includes('+') || timestamp.includes('-', 11)
        ? timestamp
        : timestamp + 'Z';
      const date = new Date(timeStr);
      // Use same format as MessageItem (main chat window)
      return date.toLocaleTimeString(undefined, {
        hour: '2-digit',
        minute: '2-digit',
        hour12: true
      });
    } catch {
      return '';
    }
  };

  // Always show panel, even when no tasks (for visibility)
  // if (tasks.length === 0 && !loading) {
  //   return null; // Don't show panel if no active tasks
  // }

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: laserScanStyle }} />
      <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-2 shadow-sm">
        {loading && (
          <div className="flex justify-end mb-1">
            <div className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
          </div>
        )}

        <div className="space-y-1.5">
          {/* Background Tasks Section - Show as "Enable Background Task" suggestions */}
          {(() => {
            // Filter background tasks that should be shown (not already enabled)
            const visibleBackgroundTasks = backgroundTasks.filter((task) => {
              const playbookCode = (task.pack_id || task.playbook_id || '').toLowerCase().trim();
              if (!playbookCode) return false; // Skip tasks without playbook code

              // Check if there's an enabled routine for this playbook
              // Use case-insensitive matching to handle any format differences
              const existingRoutine = backgroundRoutines.find(r => {
                const routineCode = (r.playbook_code || '').toLowerCase().trim();
                return routineCode === playbookCode;
              });

              // Only show if routine doesn't exist or is not enabled
              // If routine exists and is enabled, filter out this task
              if (existingRoutine && existingRoutine.enabled) {
                return false;
              }

              return true;
            });

            // Only render if there are visible background tasks
            if (visibleBackgroundTasks.length === 0) {
              return null;
            }

            return visibleBackgroundTasks.map((task) => {
              const playbookCode = task.pack_id || task.playbook_id || '';

              return (
                <div
                  key={`bg-${task.id}`}
                  className="border rounded p-2 bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700"
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-2">
                      <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 border border-gray-300 dark:border-gray-600">
                        {t('backgroundExecution' as any)}
                      </span>
                      <span className="text-xs font-medium text-gray-900 dark:text-gray-100">
                        {playbookCode}
                      </span>
                    </div>
                  </div>
                  <div className="text-xs text-gray-600 dark:text-gray-400 mb-2">
                    {t('backgroundExecutionDescription' as any)}
                  </div>
                  <button
                    onClick={async () => {
                      try {
                        const response = await fetch(
                          `${apiUrl}/api/v1/workspaces/${workspaceId}/background-routines`,
                          {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                              playbook_code: playbookCode,
                              config: {}
                            })
                          }
                        );
                        if (response.ok) {
                          // Reload routines and tasks
                          const routinesResponse = await fetch(
                            `${apiUrl}/api/v1/workspaces/${workspaceId}/background-routines`
                          );
                          if (routinesResponse.ok) {
                            const routinesData = await routinesResponse.json();
                            setBackgroundRoutines(routinesData.routines || []);
                          }
                          loadTasks();
                          window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
                        }
                      } catch (err) {
                        console.error('Failed to enable background routine:', err);
                        alert(`${t('enableFailed' as any)}: ${err instanceof Error ? err.message : t('unknownError' as any)}`);
                      }
                    }}
                    className="w-full px-2 py-1.5 text-xs font-medium text-white bg-blue-600 dark:bg-blue-700 hover:bg-blue-700 dark:hover:bg-blue-600 rounded transition-colors"
                  >
                    {t('enableBackgroundTask' as any)}
                  </button>
                </div>
              );
            });
          })()}

          {tasks.length === 0 && (() => {
            const visibleBackgroundTasks = backgroundTasks.filter((task) => {
              const playbookCode = (task.pack_id || task.playbook_id || '').toLowerCase().trim();
              if (!playbookCode) return false;
              const existingRoutine = backgroundRoutines.find(r => {
                const routineCode = (r.playbook_code || '').toLowerCase().trim();
                return routineCode === playbookCode;
              });
              return !(existingRoutine && existingRoutine.enabled);
            });
            return visibleBackgroundTasks.length === 0;
          })() ? (
            <div className="text-xs text-gray-500 dark:text-gray-400 italic py-2">
              {t('noPendingTasks' as any)}
            </div>
          ) : tasks.length > 0 ? (
            (() => {
              // Group tasks by pack_id for better organization
              const groupedTasks = tasks.reduce((acc, task) => {
                const packId = task.pack_id || 'unknown';
                if (!acc[packId]) {
                  acc[packId] = [];
                }
                acc[packId].push(task);
                return acc;
              }, {} as Record<string, typeof tasks>);

              const taskElements: React.ReactNode[] = [];

              Object.entries(groupedTasks).forEach(([packId, packTasks]) => {
                // Add compact group header if multiple tasks
                if (packTasks.length > 1) {
                  taskElements.push(
                    <div key={`group-${packId}`} className="text-xs text-gray-500 font-medium px-1 py-0.5">
                      {packId}: {packTasks.length} {t('pendingTasks' as any) || 'tasks'}
                    </div>
                  );
                }

                // Add task cards (skip background tasks and system playbooks)
                packTasks.forEach((task) => {
                  // Skip background tasks - they should be managed separately
                  const playbookCode = task.pack_id || task.playbook_id || '';
                  const backgroundPlaybookCodes = ['habit_learning'];
                  const isBackground = backgroundPlaybookCodes.includes(playbookCode.toLowerCase()) ||
                    task.result?.llm_analysis?.is_background ||
                    task.data?.execution_context?.run_mode === 'background';
                  if (isBackground) {
                    console.log('[PendingTasksPanel] Skipping background task:', task.id);
                    return; // Skip rendering background tasks
                  }

                  // Skip system playbooks - these are internal system tools and should not be shown to users
                  const systemPlaybookCodes = ['execution_status_query'];
                  if (systemPlaybookCodes.includes(playbookCode)) {
                    console.log('[PendingTasksPanel] Skipping system playbook:', playbookCode, task.id);
                    return; // Skip system playbooks - they are internal tools
                  }

                  // RUNNING tasks should not appear in pending panel - they should be in execution console
                  // Filter them out here (they are already filtered in activeTasks, but double-check for safety)
                  const isRunning = task.status?.toUpperCase() === 'RUNNING';
                  if (isRunning) {
                    console.log('[PendingTasksPanel] Skipping RUNNING task:', task.id);
                    return; // Skip RUNNING tasks - they belong in execution console, not pending panel
                  }

                  // Debug: Log task being rendered
                  console.log('[PendingTasksPanel] Rendering task:', {
                    id: task.id,
                    pack_id: task.pack_id,
                    task_type: task.task_type,
                    status: task.status
                  });

                  // For PENDING or SUCCEEDED tasks, show compact details
                  const isSucceeded = task.status?.toUpperCase() === 'SUCCEEDED';
                  const hasArtifact = artifactMap[task.id] && onViewArtifact;

                  taskElements.push(
                    <div
                      key={task.id}
                      className={`border rounded p-1.5 transition-colors ${isSucceeded
                        ? 'bg-green-50 dark:bg-green-900/20 hover:bg-green-100 dark:hover:bg-green-900/30 border-green-200 dark:border-green-800'
                        : 'bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 border-gray-200 dark:border-gray-700'
                        }`}
                    >
                      <div className="flex-1 min-w-0">
                        {/* Compact header: title + time + status badge in one line */}
                        <div className="flex items-center justify-between gap-1.5 mb-1">
                          <div className="flex items-center gap-1.5 flex-1 min-w-0">
                            <div className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate" title={task.title || task.summary || task.pack_id || task.playbook_id || task.task_type}>
                              {(() => {
                                // Debug: Log task structure to console
                                if (process.env.NODE_ENV === 'development') {
                                  console.log('[PendingTasksPanel] Task data for display:', {
                                    id: task.id,
                                    task_type: task.task_type,
                                    pack_id: task.pack_id,
                                    playbook_id: task.playbook_id,
                                    title: task.title,
                                    summary: task.summary,
                                    'task keys': Object.keys(task),
                                    'full task': task
                                  });
                                }

                                // Priority: title > summary > playbook name from i18n > pack_id/playbook_id > task_type
                                if (task.title) {
                                  console.log('[PendingTasksPanel] Using task.title:', task.title);
                                  return task.title;
                                }
                                if (task.summary) {
                                  console.log('[PendingTasksPanel] Using task.summary:', task.summary);
                                  return task.summary;
                                }
                                // Try to get playbook name from i18n metadata
                                const playbookCode = task.pack_id || task.playbook_id;
                                console.log('[PendingTasksPanel] playbookCode:', playbookCode);
                                if (playbookCode) {
                                  const playbookName = getPlaybookMetadata(playbookCode, 'name', 'zh-TW');
                                  console.log('[PendingTasksPanel] playbookName from metadata:', playbookName);
                                  if (playbookName) {
                                    return playbookName;
                                  }
                                }
                                if (task.task_type === 'suggestion') {
                                  console.log('[PendingTasksPanel] Using suggestion playbookCode:', playbookCode);
                                  return playbookCode || 'Task';
                                }
                                // For playbook execution tasks, prefer pack_id/playbook_id over task_type
                                if (playbookCode) {
                                  console.log('[PendingTasksPanel] Using playbookCode:', playbookCode);
                                  return playbookCode;
                                }
                                // Fallback to task_type only if nothing else is available
                                console.log('[PendingTasksPanel] Fallback to task_type:', task.task_type);
                                return task.task_type || 'Task';
                              })()}
                            </div>
                            {/* Background playbook indicator (check is_background flag or pack_id) */}
                            {(() => {
                              const isBackground = task.result?.llm_analysis?.is_background ||
                                (task.pack_id?.toLowerCase() === 'habit_learning');
                              if (isBackground) {
                                return (
                                  <span
                                    className="text-xs px-1 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 border border-gray-300 dark:border-gray-600 flex-shrink-0"
                                    title={t('backgroundExecutionDescription' as any)}
                                  >
                                    {t('backgroundExecution' as any)}
                                  </span>
                                );
                              }
                              // Show confidence score for non-background playbooks
                              if (task.result?.llm_analysis?.confidence !== undefined) {
                                return (
                                  <span
                                    className="text-xs px-1 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 border border-gray-400 dark:border-gray-600 flex-shrink-0"
                                    title={t('llmConfidenceScore', { confidence: task.result.llm_analysis.confidence.toFixed(2) })}
                                  >
                                    {t('confidence' as any)}{task.result.llm_analysis.confidence.toFixed(2)}
                                  </span>
                                );
                              }
                              return null;
                            })()}
                          </div>
                          {task.created_at && (
                            <div className="text-xs text-gray-400 dark:text-gray-500 flex-shrink-0">
                              {formatTime(task.created_at)}
                            </div>
                          )}
                        </div>

                        {/* AI Inferred Intent Subtitle (for suggestion tasks) */}
                        {task.task_type === 'suggestion' && task.message_id && (
                          <PlaybookIntentSubtitle
                            workspaceId={workspaceId}
                            apiUrl={apiUrl}
                            messageId={task.message_id}
                          />
                        )}

                        {/* LLM Analysis: Content tags */}
                        {task.result?.llm_analysis?.content_tags && Array.isArray(task.result.llm_analysis.content_tags) && task.result.llm_analysis.content_tags.length > 0 && (
                          <div className="flex flex-wrap gap-1 mb-1">
                            {task.result.llm_analysis.content_tags.slice(0, 3).map((tag: string, idx: number) => (
                              <span
                                key={idx}
                                className="text-xs px-1 py-0.5 rounded bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-700"
                              >
                                {tag}
                              </span>
                            ))}
                            {task.result.llm_analysis.content_tags.length > 3 && (
                              <span className="text-xs text-gray-500 dark:text-gray-400">
                                +{task.result.llm_analysis.content_tags.length - 3}
                              </span>
                            )}
                          </div>
                        )}

                        {/* LLM Analysis: Reason */}
                        {task.result?.llm_analysis?.reason && task.result.llm_analysis.reason.trim() && (
                          <div className="text-xs text-gray-600 dark:text-gray-400 mb-1 line-clamp-2">
                            {task.result.llm_analysis.reason}
                          </div>
                        )}

                        {/* Debug: Show suggestion content only (not full JSON) */}
                        {process.env.NODE_ENV === 'development' && task.result?.llm_analysis && (
                          <div className="text-[9px] text-gray-400 mt-1">
                            {task.result.llm_analysis.reason || task.result.llm_analysis.analysis_summary || 'No suggestion content'}
                          </div>
                        )}

                        {/* Artifact Creation Warning */}
                        {isSucceeded && (task as any).artifact_creation_failed && (task as any).artifact_warning && (
                          <div className="mt-1 mb-1 p-1.5 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded text-xs">
                            <div className="flex items-start gap-1.5">
                              <svg className="h-3.5 w-3.5 text-yellow-600 dark:text-yellow-400 flex-shrink-0 mt-0.5" viewBox="0 0 20 20" fill="currentColor">
                                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                              </svg>
                              <div className="flex-1 min-w-0">
                                <div className="font-medium text-yellow-800 dark:text-yellow-300 mb-0.5">未指定儲存位置</div>
                                <div className="text-yellow-700 dark:text-yellow-400 text-[10px] mb-0.5">{(task as any).artifact_warning.message}</div>
                                {(task as any).artifact_warning.action_required && (
                                  <div className="text-yellow-600 dark:text-yellow-500 text-[10px] mb-1">
                                    {(task as any).artifact_warning.action_required}
                                  </div>
                                )}
                                {/* Retry button */}
                                <button
                                  onClick={async () => {
                                    try {
                                      // Get associated timeline_item from timeline API
                                      const timelineResponse = await fetch(
                                        `${apiUrl}/api/v1/workspaces/${workspaceId}/timeline?limit=100`
                                      );
                                      if (timelineResponse.ok) {
                                        const timelineData = await timelineResponse.json();
                                        const timelineItem = timelineData.items?.find((item: any) => item.task_id === task.id);
                                        if (timelineItem) {
                                          const response = await fetch(
                                            `${apiUrl}/api/v1/workspaces/${workspaceId}/timeline-items/${timelineItem.id}/retry-artifact`,
                                            {
                                              method: 'POST',
                                              headers: { 'Content-Type': 'application/json' }
                                            }
                                          );
                                          if (response.ok) {
                                            const result = await response.json();
                                            if (result.success) {
                                              // Reload tasks
                                              loadTasks();
                                              // Trigger workspace-chat-updated event
                                              window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
                                            } else {
                                              alert(`${t('retryFailed' as any)}: ${result.error || t('unknownError' as any)}`);
                                            }
                                          } else {
                                            const error = await response.json();
                                            alert(`${t('retryFailed' as any)}: ${error.detail || t('unknownError' as any)}`);
                                          }
                                        } else {
                                          alert(t('timelineItemNotFound' as any));
                                        }
                                      } else {
                                        alert(t('timelineItemUnavailable' as any));
                                      }
                                    } catch (err: any) {
                                      alert(`${t('retryFailed' as any)}: ${err.message || t('unknownError' as any)}`);
                                    }
                                  }}
                                  className="w-full px-1.5 py-0.5 text-[10px] font-medium text-yellow-700 dark:text-yellow-400 hover:text-yellow-800 dark:hover:text-yellow-300 border border-yellow-300 dark:border-yellow-700 rounded hover:bg-yellow-100 dark:hover:bg-yellow-900/30 transition-all flex items-center justify-center gap-1"
                                >
                                  <span>🔄</span>
                                  <span>{t('retry' as any)}</span>
                                </button>
                              </div>
                            </div>
                          </div>
                        )}


                        {/* Action row - Execute button + Auto-exec config dropdown in same line */}
                        {task.pack_id && !isSucceeded && (
                          <div className="flex flex-col gap-1">
                            {/* Status message */}
                            {taskStatusMessages[task.id] && (
                              <div className="text-[10px] text-blue-600 dark:text-blue-400 px-1">
                                {taskStatusMessages[task.id]}
                              </div>
                            )}
                            <div className="flex items-center gap-1">
                              {/* Pending status badge */}
                              <span
                                className={`text-xs px-1 py-0.5 rounded border flex-shrink-0 ${getStatusColor(
                                  task.status
                                )}`}
                              >
                                {t('taskStatusPending' as any)}
                              </span>
                              {/* Execute button */}
                              <button
                                onClick={async () => {
                                  // Mark task as executing
                                  setExecutingTaskIds(prev => new Set([...Array.from(prev), task.id]));
                                  setTaskStatusMessages(prev => ({
                                    ...prev,
                                    [task.id]: t('taskStatusRunning' as any)
                                  }));

                                  try {
                                    // For suggestion tasks, use action + action_params instead of timeline_item_id
                                    const response = await fetch(
                                      `${apiUrl}/api/v1/workspaces/${workspaceId}/chat`,
                                      {
                                        method: 'POST',
                                        headers: {
                                          'Content-Type': 'application/json',
                                        },
                                        body: JSON.stringify({
                                          action: 'execute_pack',
                                          action_params: {
                                            pack_id: task.pack_id,
                                            task_id: task.id
                                          },
                                          message: '',
                                          files: [],
                                          mode: 'auto'
                                        })
                                      }
                                    );

                                    if (!response.ok) {
                                      const errorData = await response.json().catch(() => ({}));
                                      setTaskStatusMessages(prev => ({
                                        ...prev,
                                        [task.id]: `${t('executionFailed' as any)}: ${errorData.detail || `HTTP ${response.status}`}`
                                      }));
                                      console.error('Failed to execute pack:', errorData.detail || `HTTP ${response.status}`);
                                      // Still reload tasks to update UI state
                                      await loadTasks();
                                      // Trigger workspace chat update event (task will appear in timeline if completed)
                                      window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
                                      // Clear executing state after delay
                                      setTimeout(() => {
                                        setExecutingTaskIds(prev => {
                                          const newSet = new Set(prev);
                                          newSet.delete(task.id);
                                          return newSet;
                                        });
                                        setTaskStatusMessages(prev => {
                                          const updated = { ...prev };
                                          delete updated[task.id];
                                          return updated;
                                        });
                                      }, 3000);
                                      return;
                                    }

                                    setTaskStatusMessages(prev => ({
                                      ...prev,
                                      [task.id]: t('executionSuccessUpdating' as any)
                                    }));

                                    // Reload tasks after action
                                    await loadTasks();

                                    // Check if task still needs data supplementation after execution
                                    // Wait a bit for task status to update, then check
                                    setTimeout(async () => {
                                      try {
                                        const checkResponse = await fetch(
                                          `${apiUrl}/api/v1/workspaces/${workspaceId}/tasks?limit=20&include_completed=true`
                                        );
                                        if (checkResponse.ok) {
                                          const checkData = await checkResponse.json();
                                          const allTasks = checkData.tasks || [];
                                          const executedTask = allTasks.find((t: any) => t.id === task.id);

                                          // If task is still PENDING after execution, it likely needs additional data
                                          if (executedTask && (executedTask.status?.toUpperCase() === 'PENDING' || executedTask.status === 'pending')) {
                                            // Task still pending, likely needs data supplementation
                                            // Extract task title/description for context
                                            const taskTitle = task.title || task.summary || task.pack_id || '任務';
                                            const taskDescription = (task as any).description || task.summary || '';

                                            // Determine data type needed based on task type or description
                                            let dataType: 'file' | 'text' | 'both' = 'both';
                                            const desc = (taskDescription + ' ' + taskTitle).toLowerCase();
                                            if (desc.includes('上傳') || desc.includes('檔案') || desc.includes('文件') || desc.includes('upload') || desc.includes('file')) {
                                              dataType = 'file';
                                            } else if (desc.includes('輸入') || desc.includes('文字') || desc.includes('輸入') || desc.includes('text') || desc.includes('input')) {
                                              dataType = 'text';
                                            }

                                            // Trigger continue-conversation event to guide user
                                            window.dispatchEvent(new CustomEvent('continue-conversation', {
                                              detail: {
                                                type: 'continue-conversation',
                                                taskId: task.id,
                                                context: {
                                                  topic: taskTitle,
                                                  requiresData: {
                                                    type: dataType,
                                                    description: taskDescription || `任務「${taskTitle}」需要補充資料以繼續執行`,
                                                    prompt: `關於任務「${taskTitle}」，我需要補充以下資料：`
                                                  }
                                                }
                                              }
                                            }));
                                          }
                                        }
                                      } catch (err) {
                                        console.error('[PendingTasksPanel] Failed to check task status for data supplementation:', err);
                                      }
                                    }, 1000);

                                    // Trigger workspace chat update event
                                    window.dispatchEvent(new CustomEvent('workspace-chat-updated'));

                                    // Clear executing state after delay
                                    setTimeout(() => {
                                      setExecutingTaskIds(prev => {
                                        const newSet = new Set(prev);
                                        newSet.delete(task.id);
                                        return newSet;
                                      });
                                      setTaskStatusMessages(prev => {
                                        const updated = { ...prev };
                                        delete updated[task.id];
                                        return updated;
                                      });
                                    }, 2000);
                                  } catch (err: any) {
                                    setTaskStatusMessages(prev => ({
                                      ...prev,
                                      [task.id]: `${t('executionFailed' as any)}: ${err.message || t('unknownError' as any)}`
                                    }));
                                    console.error('Failed to execute suggestion action:', err);
                                    // Still reload tasks to update UI state
                                    await loadTasks();
                                    // Trigger workspace chat update event
                                    window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
                                    // Clear executing state after delay
                                    setTimeout(() => {
                                      setExecutingTaskIds(prev => {
                                        const newSet = new Set(prev);
                                        newSet.delete(task.id);
                                        return newSet;
                                      });
                                      setTaskStatusMessages(prev => {
                                        const updated = { ...prev };
                                        delete updated[task.id];
                                        return updated;
                                      });
                                    }, 3000);
                                  }
                                }}
                                disabled={executingTaskIds.has(task.id)}
                                className={`flex-1 px-2 py-1 text-xs font-medium rounded transition-all relative shadow-sm hover:shadow-md flex items-center justify-center gap-1 ${executingTaskIds.has(task.id)
                                  ? 'bg-blue-400 dark:bg-blue-600 text-white border border-blue-500 dark:border-blue-700 cursor-not-allowed opacity-75'
                                  : 'text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 border border-blue-300 dark:border-blue-700 hover:bg-blue-50 dark:hover:bg-blue-900/30'
                                  }`}
                              >
                                {executingTaskIds.has(task.id) ? (
                                  <>
                                    <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                                    <span>{t('executing' as any)}</span>
                                  </>
                                ) : (
                                  <span className="laser-scan-text" data-text={t('execute' as any)}>
                                    {t('execute' as any)}
                                  </span>
                                )}
                              </button>

                              {/* Reject button */}
                              <button
                                onClick={() => {
                                  setShowRejectDialog(task.id);
                                  setRejectReason('');
                                  setRejectComment('' as any);
                                }}
                                className="px-2 py-1 text-xs font-medium text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 border border-red-300 dark:border-red-700 rounded hover:bg-red-50 dark:hover:bg-red-900/30 transition-all flex items-center justify-center gap-1 flex-shrink-0"
                                title={t('rejectTask' as any)}
                              >
                                <span>✕</span>
                                <span>{t('reject' as any)}</span>
                              </button>

                              {/* Auto-exec config dropdown - compact */}
                              {task.result?.llm_analysis?.confidence !== undefined && task.result.llm_analysis.confidence >= 0.7 ? (
                                <select
                                  onChange={async (e) => {
                                    const value = e.target.value;
                                    if (value === 'none') {
                                      // Disable auto-exec when selecting "none"
                                      try {
                                        const response = await fetch(
                                          `${apiUrl}/api/v1/workspaces/${workspaceId}/playbook-auto-exec-config`,
                                          {
                                            method: 'PATCH',
                                            headers: {
                                              'Content-Type': 'application/json',
                                            },
                                            body: JSON.stringify({
                                              playbook_code: task.pack_id,
                                              auto_execute: false
                                            })
                                          }
                                        );
                                        if (response.ok) {
                                          window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
                                        }
                                      } catch (err: any) {
                                        console.error('Failed to disable auto-exec config:', err);
                                      }
                                      return;
                                    }

                                    try {
                                      const threshold = parseFloat(value);
                                      const response = await fetch(
                                        `${apiUrl}/api/v1/workspaces/${workspaceId}/playbook-auto-exec-config`,
                                        {
                                          method: 'PATCH',
                                          headers: {
                                            'Content-Type': 'application/json',
                                          },
                                          body: JSON.stringify({
                                            playbook_code: task.pack_id,
                                            confidence_threshold: threshold,
                                            auto_execute: true
                                          })
                                        }
                                      );

                                      if (response.ok) {
                                        // Show success feedback
                                        e.target.style.backgroundColor = '#d1fae5';
                                        setTimeout(() => {
                                          e.target.style.backgroundColor = '';
                                        }, 1000);
                                        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
                                      } else {
                                        console.error('Failed to update auto-exec config:', await response.text());
                                      }
                                    } catch (err: any) {
                                      console.error('Failed to update auto-exec config:', err);
                                    }
                                  }}
                                  value={
                                    workspace?.playbook_auto_execution_config?.[task.pack_id || '']?.auto_execute
                                      ? String(workspace.playbook_auto_execution_config[task.pack_id || ''].confidence_threshold || 0.8)
                                      : 'none'
                                  }
                                  className="px-1.5 py-1 text-[10px] text-gray-600 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors flex-shrink-0"
                                  title="設定自動執行閾值（會持久化到當前 workspace）"
                                >
                                  <option value="none">auto</option>
                                  <option value="0.9">≥0.9</option>
                                  <option value="0.8">≥0.8</option>
                                  <option value="0.7">≥0.7</option>
                                </select>
                              ) : (
                                <span
                                  className="px-1.5 py-1 text-[10px] text-gray-400 dark:text-gray-500 border border-gray-200 dark:border-gray-700 rounded bg-gray-50 dark:bg-gray-800 flex-shrink-0 cursor-not-allowed"
                                  title="信心分數需 ≥ 0.7 才能設定自動執行"
                                >
                                  auto
                                </span>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                });
              });

              return taskElements;
            })()
          ) : null}
        </div>
      </div>

      {/* Reject Task Dialog */}
      {showRejectDialog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4 shadow-xl">
            <h3 className="text-lg font-semibold mb-4 text-gray-900 dark:text-gray-100">{t('rejectTask' as any)}</h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">{t('rejectTaskConfirm' as any)}</p>

            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {t('rejectReason' as any)}
              </label>
              <select
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              >
                <option value="">{t('rejectReasonOther' as any)}</option>
                <option value="irrelevant">{t('rejectReasonIrrelevant' as any)}</option>
                <option value="duplicate">{t('rejectReasonDuplicate' as any)}</option>
                <option value="dont_want_auto">{t('rejectReasonDontWantAuto' as any)}</option>
                <option value="other">{t('rejectReasonOther' as any)}</option>
              </select>
            </div>

            {rejectReason === 'other' && (
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {t('rejectComment' as any)}
                </label>
                <textarea
                  value={rejectComment}
                  onChange={(e) => setRejectComment(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                  rows={3}
                  placeholder={t('rejectComment' as any)}
                />
              </div>
            )}

            <div className="flex justify-end gap-2">
              <button
                onClick={() => {
                  setShowRejectDialog(null);
                  setRejectReason('');
                  setRejectComment('' as any);
                }}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
              >
                {t('cancel' as any)}
              </button>
              <button
                onClick={async () => {
                  try {
                    const response = await fetch(
                      `${apiUrl}/api/v1/workspaces/${workspaceId}/tasks/${showRejectDialog}/reject`,
                      {
                        method: 'POST',
                        headers: {
                          'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                          reason_code: rejectReason || null,
                          comment: rejectComment || null,
                        }),
                      }
                    );

                    if (response.ok) {
                      const result = await response.json();
                      setRejectedTasks(prev => ({
                        ...prev,
                        [showRejectDialog]: {
                          timestamp: Date.now(),
                          canRestore: true,
                        },
                      }));

                      // Show restore countdown
                      const restoreInterval = setInterval(() => {
                        setRejectedTasks(prev => {
                          const task = prev[showRejectDialog];
                          if (!task) {
                            clearInterval(restoreInterval);
                            return prev;
                          }
                          const elapsed = Math.floor((Date.now() - task.timestamp) / 1000);
                          if (elapsed >= 10) {
                            clearInterval(restoreInterval);
                            return {
                              ...prev,
                              [showRejectDialog]: {
                                ...task,
                                canRestore: false,
                              },
                            };
                          }
                          return prev;
                        });
                      }, 1000);

                      setTimeout(() => {
                        clearInterval(restoreInterval);
                      }, 10000);

                      setShowRejectDialog(null);
                      setRejectReason('');
                      setRejectComment('' as any);
                      await loadTasks();
                      window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
                    } else {
                      const error = await response.json();
                      alert(`${t('rejectTask' as any)} failed: ${error.detail || t('unknownError' as any)}`);
                    }
                  } catch (err: any) {
                    alert(`${t('rejectTask' as any)} failed: ${err.message || t('unknownError' as any)}`);
                  }
                }}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700 transition-colors"
              >
                {t('reject' as any)}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Restore Task Notification */}
      {Object.entries(rejectedTasks).map(([taskId, taskInfo]) => {
        if (!taskInfo.canRestore) return null;
        const elapsed = Math.floor((Date.now() - taskInfo.timestamp) / 1000);
        const remaining = 10 - elapsed;
        if (remaining <= 0) return null;

        return (
          <div
            key={taskId}
            className="fixed bottom-4 right-4 bg-blue-500 dark:bg-blue-600 text-white px-4 py-3 rounded-lg shadow-lg z-50 flex items-center gap-3"
          >
            <span>{t('taskRejected' as any)}</span>
            <span className="text-sm opacity-90">{t('restoreAvailable', { seconds: String(remaining) })}</span>
            <button
              onClick={async () => {
                try {
                  const response = await fetch(
                    `${apiUrl}/api/v1/workspaces/${workspaceId}/tasks/${taskId}/restore`,
                    {
                      method: 'POST',
                      headers: {
                        'Content-Type': 'application/json',
                      },
                      body: JSON.stringify({}),
                    }
                  );

                  if (response.ok) {
                    setRejectedTasks(prev => {
                      const updated = { ...prev };
                      delete updated[taskId];
                      return updated;
                    });
                    await loadTasks();
                    window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
                  } else {
                    const error = await response.json();
                    alert(`${t('restoreTask' as any)} failed: ${error.detail || t('unknownError' as any)}`);
                  }
                } catch (err: any) {
                  alert(`${t('restoreTask' as any)} failed: ${err.message || t('unknownError' as any)}`);
                }
              }}
              className="px-3 py-1 text-sm font-medium bg-white dark:bg-gray-800 text-blue-600 dark:text-blue-400 rounded hover:bg-blue-50 dark:hover:bg-gray-700 transition-colors"
            >
              {t('restoreTask' as any)}
            </button>
          </div>
        );
      })}
    </>
  );
}


