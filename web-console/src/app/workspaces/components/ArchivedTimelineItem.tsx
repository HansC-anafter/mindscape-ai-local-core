'use client';

import React, { useState } from 'react';

interface ExecutionSession {
  execution_id: string;
  workspace_id: string;
  status: string;
  playbook_code?: string;
  trigger_source?: string;
  current_step_index: number;
  total_steps: number;
  paused_at?: string;
  origin_intent_label?: string;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  failure_type?: string;
  failure_reason?: string;
  [key: string]: any;
}

interface ArchivedTimelineItemProps {
  execution: ExecutionSession;
  onClick?: () => void;
  onOpenConsole?: () => void;
}

export default function ArchivedTimelineItem({
  execution,
  onClick,
  onOpenConsole
}: ArchivedTimelineItemProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const handleClick = () => {
    setIsExpanded(!isExpanded);
    if (onClick) {
      onClick();
    }
  };

  const handleOpenConsole = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onOpenConsole) {
      onOpenConsole();
    }
  };

  const getStatusBadge = () => {
    if (execution.status === 'succeeded') {
      return (
        <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-green-100 text-green-700 border-green-300 font-medium">
          Succeeded
        </span>
      );
    } else if (execution.status === 'failed') {
      return (
        <span className="inline-block px-1.5 py-0.5 text-xs rounded border bg-red-100 text-red-700 border-red-300 font-medium">
          Failed
        </span>
      );
    }
    return null;
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    // Convert UTC to local timezone explicitly
    return date.toLocaleString('zh-TW', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
      timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone
    });
  };

  return (
    <div
      className={`bg-gray-50 border border-gray-200 rounded p-1.5 opacity-60 hover:opacity-80 transition-all duration-200 cursor-pointer ${
        isExpanded ? 'opacity-90' : ''
      }`}
      onClick={handleClick}
    >
      {/* Compact Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className="text-xs text-gray-700 truncate font-medium">
            {execution.playbook_code || 'Playbook Execution'}
          </span>
          {execution.trigger_source && (
            <span className="text-xs px-1 py-0.5 rounded border bg-gray-100 text-gray-600 border-gray-300 flex-shrink-0">
              {execution.trigger_source}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0 ml-2">
          {getStatusBadge()}
          <svg
            className={`w-3 h-3 text-gray-500 transition-transform duration-200 ${
              isExpanded ? 'rotate-180' : ''
            }`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 9l-7 7-7-7"
            />
          </svg>
        </div>
      </div>

      {/* Expanded Details */}
      {isExpanded && (
        <div className="mt-2 pt-2 border-t border-gray-300 space-y-1.5">
          {/* Steps Information */}
          <div className="text-xs text-gray-600">
            <span className="font-medium">Steps:</span> {execution.current_step_index + 1}/{execution.total_steps}
          </div>

          {/* Intent Label */}
          {execution.origin_intent_label && (
            <div className="text-xs text-gray-600">
              <span className="font-medium">Intent:</span> {execution.origin_intent_label}
            </div>
          )}

          {/* Timestamps */}
          <div className="text-xs text-gray-500 space-y-0.5">
            {execution.created_at && (
              <div>
                <span className="font-medium">Created:</span> {formatDate(execution.created_at)}
              </div>
            )}
            {execution.started_at && (
              <div>
                <span className="font-medium">Started:</span> {formatDate(execution.started_at)}
              </div>
            )}
            {execution.completed_at && (
              <div>
                <span className="font-medium">Completed:</span> {formatDate(execution.completed_at)}
              </div>
            )}
          </div>

          {/* Failure Information */}
          {execution.status === 'failed' && (
            <div className="text-xs text-red-600 space-y-1">
              {execution.failure_type && (
                <div>
                  <span className="font-medium">失敗類型:</span> {execution.failure_type}
                </div>
              )}
              {execution.failure_reason && (
                <div>
                  <span className="font-medium">失敗原因:</span> {execution.failure_reason}
                </div>
              )}
              {/* Timeout Diagnostic Information */}
              {execution.failure_type === 'timeout' && execution.task?.execution_context?.timeout_diagnostic && (
                <div className="mt-2 pt-2 border-t border-red-300">
                  <div className="font-medium mb-1">診斷信息:</div>
                  <div className="space-y-0.5 text-gray-700">
                    {(() => {
                      const diagnostic = execution.task.execution_context.timeout_diagnostic;
                      return (
                        <>
                          <div>
                            <span className="font-medium">執行步驟數:</span> {diagnostic.steps_found || 0}
                          </div>
                          {diagnostic.steps_found === 0 ? (
                            <div className="text-orange-600 italic">
                              ⚠️ 未找到執行步驟 - Playbook 可能未啟動或卡在初始化階段
                            </div>
                          ) : diagnostic.last_step ? (
                            <div>
                              <span className="font-medium">最後步驟:</span> {diagnostic.last_step.step_name || 'unknown'}
                              {diagnostic.last_step.status && (
                                <span className="ml-2 text-gray-600">(狀態: {diagnostic.last_step.status})</span>
                              )}
                            </div>
                          ) : null}
                          {diagnostic.diagnosis && (
                            <div className="text-orange-600 italic mt-1">
                              {diagnostic.diagnosis}
                            </div>
                          )}
                        </>
                      );
                    })()}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Open Console Button */}
          {onOpenConsole && (
            <div className="pt-2 border-t border-gray-300">
              <button
                onClick={handleOpenConsole}
                className="w-full px-2 py-1 text-xs font-medium text-blue-600 hover:text-blue-700 border border-blue-300 rounded hover:bg-blue-50 transition-colors"
              >
                追蹤調度
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

