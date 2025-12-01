'use client';

import React, { useState } from 'react';

interface ExecutionSession {
  execution_id: string;
  playbook_code?: string;
  status: string;
  trigger_source?: 'auto' | 'suggestion' | 'manual';
  started_at?: string;
  completed_at?: string;
  failure_type?: string;
  failure_reason?: string;
  origin_intent_label?: string;
  origin_intent_id?: string;
}

interface RunOverviewProps {
  execution: ExecutionSession;
  playbookTitle?: string;
  playbookDescription?: string;
  errors?: Array<{
    timestamp: string;
    message: string;
    details?: any;
  }>;
}

export default function RunOverview({
  execution,
  playbookTitle,
  playbookDescription,
  errors = []
}: RunOverviewProps) {
  const [expandedErrors, setExpandedErrors] = useState(false);

  const formatDateTime = (timeStr?: string) => {
    if (!timeStr) return 'N/A';
    try {
      const date = new Date(timeStr);
      return date.toLocaleString('zh-TW', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return timeStr;
    }
  };

  const getStatusColor = (status: string) => {
    if (!status) {
      return 'text-gray-600';
    }
    switch (status.toLowerCase()) {
      case 'running':
        return 'text-blue-600';
      case 'succeeded':
      case 'completed':
        return 'text-green-600';
      case 'failed':
        return 'text-red-600';
      case 'paused':
        return 'text-yellow-600';
      default:
        return 'text-gray-600';
    }
  };

  const displayErrors = expandedErrors ? errors : errors.slice(0, 2);

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5 mb-4">
      <h2 className="text-base font-semibold text-gray-900 mb-4">Run Overview</h2>

      {execution.status === 'failed' && execution.failure_reason && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="text-sm font-semibold text-red-700 mb-1">Last Error</div>
              <div className="text-sm text-red-600">{execution.failure_reason}</div>
            </div>
            {errors.length > 0 && (
              <button
                onClick={() => setExpandedErrors(!expandedErrors)}
                className="ml-4 text-xs text-red-600 hover:text-red-700 underline"
              >
                View full log
              </button>
            )}
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 mb-4">
        {/* Playbook Info */}
        <div>
          <div className="text-sm text-gray-500 mb-1">Playbook</div>
          <div className="text-sm font-medium text-gray-900">
            {playbookTitle || execution.playbook_code || 'Unknown'}
          </div>
          {playbookDescription && (
            <div className="text-xs text-gray-500 mt-1">{playbookDescription}</div>
          )}
        </div>

        {/* Initiator */}
        <div>
          <div className="text-sm text-gray-500 mb-1">Initiator</div>
          <div className="text-sm font-medium text-gray-900">
            {execution.origin_intent_label || 'default-user'}
          </div>
        </div>

        {/* Trigger */}
        <div>
          <div className="text-sm text-gray-500 mb-1">Trigger</div>
          <div className="text-sm font-medium text-gray-900 capitalize">
            {execution.trigger_source || 'Unknown'}
          </div>
        </div>

        {/* Status */}
        <div>
          <div className="text-sm text-gray-500 mb-1">Status</div>
          <div className={`text-sm font-medium ${getStatusColor(execution.status || 'unknown')}`}>
            {execution.status || 'Unknown'}
            {execution.failure_type && (
              <span className="ml-2 text-xs text-gray-500">
                ({execution.failure_type})
              </span>
            )}
          </div>
        </div>

        {/* Started */}
        <div>
          <div className="text-sm text-gray-500 mb-1">Started</div>
          <div className="text-sm font-medium text-gray-900">
            {formatDateTime(execution.started_at)}
          </div>
        </div>

        {/* Completed / Duration */}
        {execution.completed_at ? (
          <div>
            <div className="text-sm text-gray-500 mb-1">Completed</div>
            <div className="text-sm font-medium text-gray-900">
              {formatDateTime(execution.completed_at)}
            </div>
          </div>
        ) : execution.started_at ? (
          <div>
            <div className="text-sm text-gray-500 mb-1">Duration</div>
            <div className="text-sm font-medium text-gray-900">
              {Math.floor((Date.now() - new Date(execution.started_at).getTime()) / 1000 / 60)} min
            </div>
          </div>
        ) : null}
      </div>

      {/* Error Messages (only for this run) */}
      {errors.length > 0 && (
        <div className="mt-4 pt-4 border-t border-gray-200">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm font-medium text-red-600">
              Recent Errors ({errors.length})
            </div>
            {errors.length > 2 && (
              <button
                onClick={() => setExpandedErrors(!expandedErrors)}
                className="text-xs text-blue-600 hover:text-blue-700"
              >
                {expandedErrors ? 'Show Less' : 'Show All'}
              </button>
            )}
          </div>
          <div className="space-y-2">
            {displayErrors.map((error, idx) => (
              <div key={idx} className="bg-red-50 border border-red-200 rounded p-2 text-xs">
                <div className="text-red-700 font-medium mb-1">
                  {formatDateTime(error.timestamp)}
                </div>
                <div className="text-red-600 whitespace-pre-wrap break-words">
                  {error.message}
                </div>
                {error.details && expandedErrors && (
                  <details className="mt-2">
                    <summary className="text-red-500 cursor-pointer">Details</summary>
                    <pre className="mt-1 text-xs overflow-auto">
                      {JSON.stringify(error.details, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

    </div>
  );
}

