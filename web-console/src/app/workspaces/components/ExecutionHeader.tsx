'use client';

import React from 'react';
import { useT } from '@/lib/i18n';

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
}

interface ExecutionHeaderProps {
  execution: ExecutionSession;
  playbookTitle?: string;
  onRetry?: () => void;
  onStop?: () => void | Promise<void>;
  onEditPlaybook?: () => void;
  isStopping?: boolean;
}

export default function ExecutionHeader({
  execution,
  playbookTitle,
  onRetry,
  onStop,
  onEditPlaybook,
  isStopping = false
}: ExecutionHeaderProps) {
  const t = useT();
  const getStatusBadge = (status: string) => {
    if (!status) {
      return { label: t('executionStatusUnknown'), color: 'bg-gray-100 text-gray-700 border-gray-300' };
    }
    switch (status.toLowerCase()) {
      case 'running':
        return { label: t('executionStatusRunning'), color: 'bg-blue-100 text-blue-700 border-blue-300' };
      case 'succeeded':
      case 'completed':
        return { label: t('executionStatusSucceeded'), color: 'bg-green-100 text-green-700 border-green-300' };
      case 'failed':
        return { label: t('executionStatusFailed'), color: 'bg-red-100 text-red-700 border-red-300' };
      case 'paused':
        return { label: t('executionStatusPaused'), color: 'bg-yellow-100 text-yellow-700 border-yellow-300' };
      default:
        return { label: status, color: 'bg-gray-100 text-gray-700 border-gray-300' };
    }
  };

  const getTriggerSourceBadge = (source?: string) => {
    switch (source) {
      case 'auto':
        return { label: t('triggerSourceAuto'), color: 'bg-blue-100 text-blue-700 border-blue-300' };
      case 'suggestion':
        return { label: t('triggerSourceSuggested'), color: 'bg-purple-100 text-purple-700 border-purple-300' };
      case 'manual':
        return { label: t('triggerSourceManual'), color: 'bg-gray-100 text-gray-700 border-gray-300' };
      default:
        return { label: t('triggerSourceUnknown'), color: 'bg-gray-100 text-gray-700 border-gray-300' };
    }
  };

  const statusBadge = getStatusBadge(execution.status || 'unknown');
  const triggerBadge = getTriggerSourceBadge(execution.trigger_source);
  const runNumber = execution.execution_id.slice(-8);

  const formatTime = (timeStr?: string) => {
    if (!timeStr) return '';
    try {
      const date = new Date(timeStr);
      return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    } catch {
      return '';
    }
  };

  return (
    <div className="bg-white border-b border-gray-200 px-6 py-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className="flex items-center gap-2 min-w-0">
            <h1 className="text-base font-semibold text-gray-900 truncate">
              {playbookTitle || execution.playbook_code || t('unknownPlaybook')}
            </h1>
            <span className="text-xs text-gray-500 whitespace-nowrap">
              {t('runNumber', { number: runNumber })}
            </span>
          </div>

          <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium border ${statusBadge.color} whitespace-nowrap`}>
            {statusBadge.label}
          </span>

          <div className="flex items-center gap-1.5 text-xs text-gray-600 whitespace-nowrap">
            <span>{t('stepProgress', { current: (execution.current_step_index ?? 0) + 1, total: execution.total_steps || 1 })}</span>
          </div>

          <div className="flex items-center gap-1.5 text-[10px] text-gray-500">
            <span className={`px-1.5 py-0.5 rounded text-[10px] border ${triggerBadge.color}`}>
              {triggerBadge.label}
            </span>
            <span className="text-gray-400">·</span>
            <span>{t('byUser', { user: execution.initiator_user_id || t('unknownUser') })}</span>
            {execution.started_at && (
              <>
                <span className="text-gray-400">·</span>
                <span>{t('startedAt', { time: formatTime(execution.started_at) })}</span>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1.5 ml-4">
          {execution.status === 'failed' && onRetry && (
            <button
              onClick={onRetry}
              className="px-2.5 py-1 text-xs font-medium text-blue-700 bg-blue-50 border border-blue-200 rounded-md hover:bg-blue-100 transition-colors"
            >
              {t('retry')}
            </button>
          )}
          {execution.status === 'running' && onStop && (
            <button
              onClick={onStop}
              disabled={isStopping}
              className="px-2.5 py-1 text-xs font-medium text-red-700 bg-red-50 border border-red-200 rounded-md hover:bg-red-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
            >
              {isStopping ? (
                <>
                  <span className="inline-block w-3 h-3 border-2 border-red-700 border-t-transparent rounded-full animate-spin"></span>
                  <span>{t('stopping')}</span>
                </>
              ) : (
                <span>{t('stop')}</span>
              )}
            </button>
          )}
        </div>
      </div>

      {execution.status === 'failed' && execution.failure_reason && (
        <div className="mt-3 pt-3 border-t border-gray-200">
          <p className="text-sm text-red-600">
            <span className="font-medium">{t('errorLabel')}</span> {execution.failure_reason}
          </p>
        </div>
      )}
    </div>
  );
}

