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
  const [loading, setLoading] = useState(true);
  const [updatingIds, setUpdatingIds] = useState<Set<string>>(new Set());

  const loadRoutines = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/background-routines`
      );
      if (response.ok) {
        const data = await response.json();
        setRoutines(data.routines || []);
      }
    } catch (err) {
      console.error('Failed to load background routines:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRoutines();

    // Listen for workspace updates
    const handleUpdate = () => {
      loadRoutines();
    };
    window.addEventListener('workspace-chat-updated', handleUpdate);

    // Listen for tool status changes (affects readiness status)
    const cleanupToolStatus = listenToToolStatusChanged(() => {
      loadRoutines();
    });

    // Listen for background routine status changes
    const cleanupRoutineStatus = listenToBackgroundRoutineStatusChanged(() => {
      loadRoutines();
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
        await loadRoutines();
        window.dispatchEvent(new CustomEvent('workspace-chat-updated'));
        // Dispatch background routine status changed event
        dispatchBackgroundRoutineStatusChanged(workspaceId, routine.id);
      } else {
        const error = await response.json();
        alert(`${t('operationFailed')}: ${error.detail || t('unknownError')}`);
      }
    } catch (err) {
      console.error('Failed to toggle routine:', err);
      alert(`${t('operationFailed')}: ${err instanceof Error ? err.message : t('unknownError')}`);
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
        <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-gray-100 text-gray-600 border-gray-300 font-medium">
          {t('disabled')}
        </span>
      );
    }

    // Show readiness status if available
    if (routine.readiness_status) {
      if (routine.readiness_status === 'ready') {
        if (routine.last_status === 'ok') {
          return (
            <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-green-100 text-green-700 border-green-300 font-medium">
              {t('runningNormally')}
            </span>
          );
        }
        return (
          <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-green-100 text-green-700 border-green-300 font-medium">
            {t('ready')}
          </span>
        );
      } else if (routine.readiness_status === 'needs_setup') {
        return (
          <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-yellow-100 text-yellow-700 border-yellow-300 font-medium">
            {t('needsSetup')}
          </span>
        );
      } else if (routine.readiness_status === 'unsupported') {
        return (
          <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-red-100 text-red-700 border-red-300 font-medium">
            {t('unsupported')}
          </span>
        );
      }
    }

    // Fallback to legacy status
    if (routine.last_status === 'ok') {
      return (
        <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-green-100 text-green-700 border-green-300 font-medium">
          {t('runningNormally')}
        </span>
      );
    } else if (routine.last_status === 'failed') {
      return (
        <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-red-100 text-red-700 border-red-300 font-medium">
          {t('executionFailed')}
        </span>
      );
    }

    return (
      <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-blue-100 text-blue-700 border-blue-300 font-medium">
        {t('enabled')}
      </span>
    );
  };

  if (loading) {
    return (
      <div className="p-4 flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-2">
      <div className="space-y-2">
        {routines.length === 0 ? (
          <div className="text-xs text-gray-500 italic py-4 text-center">
            {t('noBackgroundTasks')}
          </div>
        ) : (
          routines.map((routine) => (
            <div
              key={routine.id}
              className={`border rounded p-2 transition-colors ${
                routine.enabled
                  ? 'bg-gray-50 border-gray-200'
                  : 'bg-gray-50 border-gray-200 opacity-60'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2 flex-1 min-w-0">
                  <span className="text-xs font-medium text-gray-900 truncate">
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
                      ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                      : routine.enabled
                      ? 'bg-red-100 text-red-700 hover:bg-red-200 border border-red-300'
                      : 'bg-blue-100 text-blue-700 hover:bg-blue-200 border border-blue-300'
                  }`}
                >
                  {updatingIds.has(routine.id)
                    ? t('processing')
                    : routine.enabled
                    ? t('disable')
                    : t('enable')}
                </button>
              </div>

              {/* Tool Status Chips */}
              {routine.tool_statuses && Object.keys(routine.tool_statuses).length > 0 && (
                <div className="mt-2 pt-2 border-t border-gray-200">
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
              <div className="text-xs text-gray-600 space-y-1 mt-2">
                {routine.last_run_at && (
                  <div>
                    <span className="font-medium">{t('lastExecution')}:</span>
                    {formatDate(routine.last_run_at)}
                  </div>
                )}
                {routine.next_run_at && routine.enabled && (
                  <div>
                    <span className="font-medium">{t('nextExecution')}:</span>
                    {formatDate(routine.next_run_at)}
                  </div>
                )}
                {routine.last_status === 'failed' && (
                  <div className="text-red-600 text-[10px] mt-1">
                    {t('lastExecutionFailed')}
                  </div>
                )}
                {routine.readiness_status === 'needs_setup' && (
                  <div className="text-yellow-600 text-[10px] mt-1">
                    {t('toolsNeedConfiguration')}
                  </div>
                )}
                {routine.readiness_status === 'unsupported' && (
                  <div className="text-red-600 text-[10px] mt-1">
                    {t('requiredToolsNotSupported')}
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

