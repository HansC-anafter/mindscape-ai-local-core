'use client';

import React from 'react';
import { useT } from '@/lib/i18n';
import { parseServerTimestamp } from '@/lib/time';
import { RunProvenanceChips, ExecutionProvenance } from './RunProvenanceChips';
import { useParams } from 'next/navigation';
import type { RemoteExecutionAggregate } from './execution-inspector/types/execution';

interface ExecutionSession {
  execution_id: string;
  playbook_code?: string;
  status: string;
  trigger_source?: 'auto' | 'suggestion' | 'manual';
  current_step_index: number;
  total_steps: number;
  started_at?: string;
  failure_type?: string;
  failure_reason?: string;
  initiator_user_id?: string;
  provenance?: ExecutionProvenance; // Web generation provenance data
}

interface ExecutionHeaderProps {
  execution: ExecutionSession;
  playbookTitle?: string;
  workspaceName?: string;
  projectName?: string;
  executionRunNumber?: number;
  stats?: {
    concurrent: number;
    waitingConfirmation: number;
    completed: number;
  };
  remoteExecutionAggregate?: RemoteExecutionAggregate;
  onRetry?: () => void;
  onStop?: () => void | Promise<void>;
  onEditPlaybook?: () => void;
  isStopping?: boolean;
}

export default function ExecutionHeader({
  execution,
  playbookTitle,
  workspaceName,
  projectName,
  executionRunNumber,
  stats,
  remoteExecutionAggregate,
  onRetry,
  onStop,
  onEditPlaybook,
  isStopping = false
}: ExecutionHeaderProps) {
  const t = useT();
  const params = useParams();
  const workspaceId = params?.workspaceId as string;
  const getStatusBadge = (status: string) => {
    if (!status) {
      return { label: t('executionStatusUnknown' as any), color: 'bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-300 border-default dark:border-gray-600' };
    }
    switch (status.toLowerCase()) {
      case 'running':
        return { label: t('executionStatusRunning' as any), color: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700' };
      case 'succeeded':
      case 'completed':
        return { label: t('executionStatusSucceeded' as any), color: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border-green-300 dark:border-green-700' };
      case 'failed':
        return { label: t('executionStatusFailed' as any), color: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-300 dark:border-red-700' };
      case 'cancelled':
      case 'cancelled_by_user':
        return { label: t('executionStatusCancelled' as any) || '已取消', color: 'bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-300 border-default dark:border-gray-600' };
      case 'paused':
        return { label: t('executionStatusPaused' as any), color: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 border-yellow-300 dark:border-yellow-700' };
      default:
        return { label: status, color: 'bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-300 border-default dark:border-gray-600' };
    }
  };

  const getTriggerSourceBadge = (source?: string) => {
    switch (source) {
      case 'auto':
        return { label: t('triggerSourceAuto' as any), color: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700' };
      case 'suggestion':
        return { label: t('triggerSourceSuggested' as any), color: 'bg-surface-secondary dark:bg-gray-800/30 text-primary dark:text-gray-300 border-default dark:border-gray-600' };
      case 'manual':
        return { label: t('triggerSourceManual' as any), color: 'bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-300 border-default dark:border-gray-600' };
      default:
        return { label: t('triggerSourceUnknown' as any), color: 'bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-300 border-default dark:border-gray-600' };
    }
  };

  const statusBadge = getStatusBadge(execution.status || 'unknown');
  const triggerBadge = getTriggerSourceBadge(execution.trigger_source);
  const runNumber = execution.execution_id.slice(-8);

  const formatTime = (timeStr?: string) => {
    if (!timeStr) return '';
    const date = parseServerTimestamp(timeStr);
    if (!date) return '';
    return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  };

  const displayRunNumber = executionRunNumber || parseInt(execution.execution_id.slice(-8), 16) % 10 + 1;

  return (
    <div className="bg-surface-accent dark:bg-gray-900 border-b border-default dark:border-gray-800 px-6 py-3">
      {/* Breadcrumb - Always show for navigation context */}
      <div className="flex items-center gap-2 text-xs text-secondary dark:text-gray-400 mb-2">
        <span className="text-secondary dark:text-gray-500">Workspace</span>
        <span className="text-tertiary dark:text-gray-500">/</span>
        <span className="text-primary dark:text-gray-300">{workspaceName || '...'}</span>

        {projectName && (
          <>
            <span className="text-tertiary dark:text-gray-500">/</span>
            <span className="text-secondary dark:text-gray-500">Project：</span>
            <span className="text-primary dark:text-gray-300">{projectName}</span>
          </>
        )}

        <span className="text-tertiary dark:text-gray-500">/</span>
        <span className="text-secondary dark:text-gray-500">Playbook：</span>
        <span className="text-primary dark:text-gray-300">{playbookTitle || execution.playbook_code || '...'}</span>

        <span className="text-tertiary dark:text-gray-500">/</span>
        <span className="text-secondary dark:text-gray-500">Execution</span>
        <span className="text-primary dark:text-gray-300 font-medium">#{displayRunNumber}</span>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className="flex items-center gap-2 min-w-0">
            <h1 className="text-base font-semibold text-primary dark:text-gray-100 truncate">
              {playbookTitle || execution.playbook_code || t('unknownPlaybook' as any)}
            </h1>
            <span className="text-xs text-secondary dark:text-gray-400 whitespace-nowrap">
              {t('runNumber', { number: String(runNumber) })}
            </span>
          </div>

          <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium border ${statusBadge.color} whitespace-nowrap`}>
            {statusBadge.label}
          </span>

          <div className="flex items-center gap-1.5 text-xs text-secondary dark:text-gray-400 whitespace-nowrap">
            <span>{t('stepProgress', { current: String((execution.current_step_index ?? 0) + 1), total: String(execution.total_steps || 1) })}</span>
          </div>

          <div className="flex items-center gap-1.5 text-[10px] text-secondary dark:text-gray-400">
            <span className={`px-1.5 py-0.5 rounded text-[10px] border ${triggerBadge.color}`}>
              {triggerBadge.label}
            </span>
            <span className="text-tertiary dark:text-gray-500">·</span>
            <span>{t('byUser', { user: execution.initiator_user_id || t('unknownUser' as any) })}</span>
            {execution.started_at && (
              <>
                <span className="text-tertiary dark:text-gray-500">·</span>
                <span>{t('startedAt', { time: formatTime(execution.started_at) })}</span>
              </>
            )}
          </div>
        </div>

        <div className="ml-4 flex flex-wrap items-center justify-end gap-2">
          {/* Summary stats */}
          {stats && (
            <div className="flex flex-wrap items-center gap-3 text-xs text-secondary dark:text-gray-400">
              {stats.concurrent > 0 && (
                <span className="flex items-center gap-1">
                  <span>🔄</span>
                  <span>{stats.concurrent} {t('concurrent' as any) || 'concurrent'}</span>
                </span>
              )}
              {stats.waitingConfirmation > 0 && (
                <span className="flex items-center gap-1 text-yellow-600 dark:text-yellow-400">
                  <span>⏸️</span>
                  <span>{stats.waitingConfirmation} {t('waitingConfirmation' as any) || 'waiting confirmation'}</span>
                </span>
              )}
              {stats.completed > 0 && (
                <span className="flex items-center gap-1">
                  <span>✅</span>
                  <span>{stats.completed} {t('completed' as any) || 'completed'}</span>
                </span>
              )}
            </div>
          )}

          {remoteExecutionAggregate && remoteExecutionAggregate.totalRemoteChildren > 0 && (
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-secondary dark:text-gray-400">
              <span className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-blue-700 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300">
                <span>GPU</span>
                <span>{remoteExecutionAggregate.totalRemoteChildren}</span>
              </span>
              {remoteExecutionAggregate.replayAttempts > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-amber-700 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
                  <span>Replay</span>
                  <span>{remoteExecutionAggregate.replayAttempts}</span>
                </span>
              )}
            </div>
          )}

          {/* Action buttons */}
          <div className="flex items-center gap-1.5">
            {execution.status === 'failed' && onRetry && (
              <button
                onClick={onRetry}
                className="px-2.5 py-1 text-xs font-medium text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-700 rounded-md hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-colors"
              >
                {t('retry' as any)}
              </button>
            )}
            {execution.status === 'running' && onStop && (
              <button
                onClick={onStop}
                disabled={isStopping}
                className="px-2.5 py-1 text-xs font-medium text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 rounded-md hover:bg-red-100 dark:hover:bg-red-900/40 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
              >
                {isStopping ? (
                  <>
                    <span className="inline-block w-3 h-3 border-2 border-red-700 dark:border-red-500 border-t-transparent rounded-full animate-spin"></span>
                    <span>{t('stopping' as any)}</span>
                  </>
                ) : (
                  <span>{t('stop' as any)}</span>
                )}
              </button>
            )}
          </div>
        </div>
      </div>

      {execution.status === 'failed' && execution.failure_reason && (
        <div className="mt-3 pt-3 border-t border-default dark:border-gray-700">
          <p className="text-sm text-red-600 dark:text-red-400">
            <span className="font-medium">{t('errorLabel' as any)}</span> {execution.failure_reason}
          </p>
        </div>
      )}

      {/* Web Generation Provenance */}
      {execution.provenance && (
        <RunProvenanceChips
          provenance={execution.provenance}
          workspaceId={workspaceId || ''}
        />
      )}
    </div>
  );
}
