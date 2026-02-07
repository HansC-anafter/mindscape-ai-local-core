'use client';

import React, { useState, useEffect } from 'react';
import { useT } from '@/lib/i18n';
import { ToolStatusChip } from '@/components/ToolStatusChip';
import { dispatchBackgroundRoutineStatusChanged, listenToBackgroundRoutineStatusChanged, listenToToolStatusChanged } from '@/lib/tool-status-events';

interface BackgroundRoutine {
  id: string;
  workspace_id: string;
  playbook_code: string;
  enabled: boolean;
  config: Record<string, any>;
  last_run_at?: string;
  next_run_at?: string;
  last_status?: string;
  readiness_status?: 'ready' | 'needs_setup' | 'unsupported';
  tool_statuses?: Record<string, string>;
  created_at: string;
  updated_at: string;
}

interface SystemTool {
  playbook_code: string;
  name: string;
  description: string;
  kind: 'system_tool';
}

interface BackgroundTasksPanelProps {
  workspaceId: string;
  apiUrl: string;
}

export default function BackgroundTasksPanel({
  workspaceId,
  apiUrl
}: BackgroundTasksPanelProps) {
  const t = useT();
  const [routines, setRoutines] = useState<BackgroundRoutine[]>([]);
  const [systemTools, setSystemTools] = useState<SystemTool[]>([]);
  const [loading, setLoading] = useState(true);
  const [updatingIds, setUpdatingIds] = useState<Set<string>>(new Set());

  const loadRoutines = async () => {
    try {
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/background-routines`
      );
      if (response.ok) {
        const data = await response.json();
        setRoutines(data.routines || []);
      }
    } catch (err) {
      console.error('Failed to load background routines:', err);
    }
  };

  const loadSystemTools = async () => {
    try {
      const response = await fetch(`${apiUrl}/api/v1/playbooks`);
      if (response.ok) {
        const allPlaybooks = await response.json();
        const systemToolPlaybooks = allPlaybooks.filter((pb: any) => {
          const kind = pb.kind;
          return kind === 'system_tool' || kind === 'SYSTEM_TOOL';
        });
        setSystemTools(systemToolPlaybooks.map((pb: any) => ({
          playbook_code: pb.playbook_code,
          name: pb.name || pb.playbook_code,
          description: pb.description || '',
          kind: 'system_tool' as const
        })));
      }
    } catch (err) {
      console.error('Failed to load system tools:', err);
    }
  };

  const loadAll = async () => {
    try {
      setLoading(true);
      await Promise.all([loadRoutines(), loadSystemTools()]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();

    // Listen for workspace updates
    const handleUpdate = () => {
      loadAll();
    };
    window.addEventListener('workspace-chat-updated', handleUpdate);

    // Listen for tool status changes (affects readiness status)
    const cleanupToolStatus = listenToToolStatusChanged(() => {
      loadAll();
    });

    // Listen for background routine status changes
    const cleanupRoutineStatus = listenToBackgroundRoutineStatusChanged(() => {
      loadAll();
    }, workspaceId);

    return () => {
      window.removeEventListener('workspace-chat-updated', handleUpdate);
      cleanupToolStatus();
      cleanupRoutineStatus();
    };
  }, [workspaceId, apiUrl]);

  const toggleRoutine = async (routine: BackgroundRoutine) => {
    if (updatingIds.has(routine.id)) return;

    setUpdatingIds(prev => new Set([...Array.from(prev), routine.id]));

    try {
      let response: Response;

      if (!routine.enabled) {
        // Enable: use new enable endpoint with tool dependency check
        response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/background-routines/${routine.id}/enable`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
          }
        );
      } else {
        // Disable: use regular update endpoint
        response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/background-routines/${routine.id}`,
          {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              enabled: false
            })
          }
        );
      }

      if (response.ok) {
        await loadAll();
        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
        // Dispatch background routine status changed event
        dispatchBackgroundRoutineStatusChanged(workspaceId, routine.id);
      } else {
        const error = await response.json();
        alert(`${t('operationFailed' as any)}: ${error.detail || t('unknownError' as any)}`);
      }
    } catch (err) {
      console.error('Failed to toggle routine:', err);
      alert(`${t('operationFailed' as any)}: ${err instanceof Error ? err.message : t('unknownError' as any)}`);
    } finally {
      setUpdatingIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(routine.id);
        return newSet;
      });
    }
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'N/A';
    try {
      const date = new Date(dateString);
      return date.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return 'N/A';
    }
  };

  const getStatusBadge = (routine: BackgroundRoutine) => {
    if (!routine.enabled) {
      return (
        <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 border-gray-300 dark:border-gray-600 font-medium">
          {t('disabled' as any)}
        </span>
      );
    }

    // Show readiness status if available
    if (routine.readiness_status) {
      if (routine.readiness_status === 'ready') {
        if (routine.last_status === 'ok') {
          return (
            <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border-green-300 dark:border-green-700 font-medium">
              {t('runningNormally' as any)}
            </span>
          );
        }
        return (
          <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border-green-300 dark:border-green-700 font-medium">
            {t('ready' as any)}
          </span>
        );
      } else if (routine.readiness_status === 'needs_setup') {
        return (
          <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 border-yellow-300 dark:border-yellow-700 font-medium">
            {t('needsSetup' as any)}
          </span>
        );
      } else if (routine.readiness_status === 'unsupported') {
        return (
          <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-300 dark:border-red-700 font-medium">
            {t('unsupported' as any)}
          </span>
        );
      }
    }

    // Fallback to legacy status
    if (routine.last_status === 'ok') {
      return (
        <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border-green-300 dark:border-green-700 font-medium">
          {t('runningNormally' as any)}
        </span>
      );
    } else if (routine.last_status === 'failed') {
      return (
        <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-300 dark:border-red-700 font-medium">
          {t('executionFailed' as any)}
        </span>
      );
    }

    return (
      <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700 font-medium">
        {t('enabled' as any)}
      </span>
    );
  };

  if (loading) {
    return (
      <div className="p-4 flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-blue-600 dark:border-blue-500 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  const totalItems = routines.length + systemTools.length;

  return (
    <div className="h-full overflow-y-auto p-2">
      <div className="space-y-2">
        {/* Background Routines Section */}
        {routines.length > 0 && (
          <>
            {routines.length > 0 && systemTools.length > 0 && (
              <div className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2 pt-2 border-t border-gray-200 dark:border-gray-700">
                {t('backgroundRoutines' as any)}
              </div>
            )}
            {routines.map((routine) => (
              <div
                key={routine.id}
                className={`border rounded p-2 transition-colors ${
                  routine.enabled
                    ? 'bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700'
                    : 'bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700 opacity-60'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 flex-1 min-w-0">
                    <span className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate">
                      {routine.playbook_code}
                    </span>
                    {getStatusBadge(routine)}
                  </div>

                  {/* Enable/Disable Toggle */}
                  <button
                    onClick={() => toggleRoutine(routine)}
                    disabled={updatingIds.has(routine.id)}
                    className={`px-2 py-1 text-xs font-medium rounded transition-colors flex-shrink-0 ${
                      updatingIds.has(routine.id)
                        ? 'bg-gray-300 dark:bg-gray-600 text-gray-500 dark:text-gray-400 cursor-not-allowed'
                        : routine.enabled
                        ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-900/40 border border-red-300 dark:border-red-700'
                        : 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-900/40 border border-blue-300 dark:border-blue-700'
                    }`}
                  >
                    {updatingIds.has(routine.id)
                      ? t('processing' as any)
                      : routine.enabled
                      ? t('disable' as any)
                      : t('enable' as any)}
                  </button>
                </div>

                {/* Tool Status Chips */}
                {routine.tool_statuses && Object.keys(routine.tool_statuses).length > 0 && (
                  <div className="mt-2 pt-2 border-t border-gray-200 dark:border-gray-700">
                    <div className="flex flex-wrap gap-1">
                      {Object.entries(routine.tool_statuses).map(([toolType, status]) => (
                        <ToolStatusChip
                          key={toolType}
                          toolType={toolType}
                          status={status as 'unavailable' | 'registered_but_not_connected' | 'connected'}
                          onClick={() => {
                            // Navigate to tools settings page
                            window.location.href = '/settings?tab=tools';
                          }}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* Routine Details */}
                <div className="text-xs text-gray-600 dark:text-gray-400 space-y-1 mt-2">
                  {routine.last_run_at && (
                    <div>
                      <span className="font-medium">{t('lastExecution' as any)}:</span>
                      {formatDate(routine.last_run_at)}
                    </div>
                  )}
                  {routine.next_run_at && routine.enabled && (
                    <div>
                      <span className="font-medium">{t('nextExecution' as any)}:</span>
                      {formatDate(routine.next_run_at)}
                    </div>
                  )}
                  {routine.last_status === 'failed' && (
                    <div className="text-red-600 dark:text-red-400 text-[10px] mt-1">
                      {t('lastExecutionFailed' as any)}
                    </div>
                  )}
                  {routine.readiness_status === 'needs_setup' && (
                    <div className="text-yellow-600 dark:text-yellow-400 text-[10px] mt-1">
                      {t('toolsNeedConfiguration' as any)}
                    </div>
                  )}
                  {routine.readiness_status === 'unsupported' && (
                    <div className="text-red-600 dark:text-red-400 text-[10px] mt-1">
                      {t('requiredToolsNotSupported' as any)}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </>
        )}

        {/* System Tools Section */}
        {systemTools.length > 0 && (
          <>
            {routines.length > 0 && systemTools.length > 0 && (
              <div className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2 pt-2 border-t border-gray-200 dark:border-gray-700">
                {t('systemTools' as any) || 'System Tools'}
              </div>
            )}
            {systemTools.map((tool) => (
              <div
                key={tool.playbook_code}
                className="border rounded p-2 bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-gray-900 dark:text-gray-100 truncate flex-1 min-w-0">
                    {tool.name || tool.playbook_code}
                  </span>
                  <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700 font-medium ml-2 flex-shrink-0">
                    {t('systemTool' as any) || 'System Tool'}
                  </span>
                </div>
                {tool.description && (
                  <div className="text-xs text-gray-600 dark:text-gray-400 mt-2">
                    {tool.description}
                  </div>
                )}
              </div>
            ))}
          </>
        )}

        {/* Empty State */}
        {totalItems === 0 && (
          <div className="text-xs text-gray-500 dark:text-gray-400 italic py-4 text-center">
            {t('noBackgroundTasks' as any)}
          </div>
        )}
      </div>
    </div>
  );
}

