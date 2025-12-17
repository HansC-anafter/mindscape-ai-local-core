'use client';

import React, { useState, useRef, useEffect } from 'react';
import { useT } from '@/lib/i18n';

interface ExecutionSummary {
  executionId: string;
  runNumber: number;
  status: 'queued' | 'running' | 'paused' | 'completed' | 'failed';
  currentStep: {
    index: number;
    name: string;
    status: 'running' | 'waiting_confirmation';
  };
  totalSteps: number;
}

interface ExecutionOverviewCardProps {
  execution: ExecutionSummary;
  isFocused: boolean;
  onFocus: () => void;
  onConfirm?: () => void;
  onReject?: () => void;
  onPause?: () => void;
  onCancel?: () => void;
  onViewDetail?: () => void;
  onRetry?: () => void;
}

export default function ExecutionOverviewCard({
  execution,
  isFocused,
  onFocus,
  onConfirm,
  onReject,
  onPause,
  onCancel,
  onViewDetail,
  onRetry
}: ExecutionOverviewCardProps) {
  const t = useT();
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowDropdown(false);
      }
    };

    if (showDropdown) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showDropdown]);

  const statusLabels: Record<string, string> = {
    queued: t('queued') || 'Queued',
    running: t('running') || 'Running',
    paused: t('paused') || 'Paused',
    completed: t('completed') || 'Completed',
    failed: t('failed') || 'Failed'
  };

  const getPrimaryAction = () => {
    switch (execution.status) {
      case 'paused':
        return {
          label: t('confirmContinue') || 'Confirm Continue',
          onClick: onConfirm,
          className: 'bg-blue-600 hover:bg-blue-700 text-white'
        };
      case 'running':
        return {
          label: t('viewDetail') || 'View Detail',
          onClick: onViewDetail || onFocus,
          className: 'bg-blue-600 hover:bg-blue-700 text-white'
        };
      case 'completed':
        return {
          label: t('viewResult') || 'View Result',
          onClick: onViewDetail || onFocus,
          className: 'bg-green-600 hover:bg-green-700 text-white'
        };
      case 'failed':
        return {
          label: t('retry') || 'Retry',
          onClick: onRetry,
          className: 'bg-blue-600 hover:bg-blue-700 text-white'
        };
      default:
        return null;
    }
  };

  const primaryAction = getPrimaryAction();
  const progressPercentage = execution.totalSteps > 0
    ? (execution.currentStep.index / execution.totalSteps) * 100
    : 0;

  return (
    <div
      className={`p-3 rounded-lg border transition-all cursor-pointer ${
        isFocused
          ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-300 dark:border-blue-700'
          : 'bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
      }`}
      onClick={onFocus}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-gray-900 dark:text-gray-100">
            Execution #{execution.runNumber}
          </span>
          <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${
            execution.status === 'running'
              ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
              : execution.status === 'paused'
              ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300'
              : execution.status === 'completed'
              ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
              : execution.status === 'failed'
              ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
              : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
          }`}>
            {statusLabels[execution.status]}
          </span>
        </div>
      </div>

      <div className="mb-2">
        <div className="text-xs text-gray-600 dark:text-gray-400 mb-1">
          Step {execution.currentStep.index}: {execution.currentStep.name}
        </div>
        <div className="h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-blue-500 dark:bg-blue-400 transition-all"
            style={{ width: `${progressPercentage}%` }}
          />
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-500 mt-1">
          {Math.round(progressPercentage)}%
        </div>
      </div>

      <div className="flex items-center gap-2">
        {primaryAction && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              primaryAction.onClick?.();
            }}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${primaryAction.className}`}
          >
            {primaryAction.label}
          </button>
        )}

        <div className="relative ml-auto" ref={dropdownRef}>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setShowDropdown(!showDropdown);
            }}
            className="px-2 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
          >
            ⋯
          </button>

          {showDropdown && (
            <div className="absolute right-0 mt-1 w-48 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md shadow-lg z-10">
              <div className="py-1">
                {execution.status === 'paused' && onReject && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onReject();
                      setShowDropdown(false);
                    }}
                    className="w-full text-left px-4 py-2 text-xs text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
                  >
                    {t('reject') || 'Reject'}
                  </button>
                )}
                {execution.status === 'running' && (
                  <>
                    {onPause && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onPause();
                          setShowDropdown(false);
                        }}
                        className="w-full text-left px-4 py-2 text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                      >
                        {t('pause') || 'Pause'}
                      </button>
                    )}
                    {onCancel && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onCancel();
                          setShowDropdown(false);
                        }}
                        className="w-full text-left px-4 py-2 text-xs text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
                      >
                        {t('cancel') || 'Cancel'}
                      </button>
                    )}
                  </>
                )}
                {onViewDetail && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onViewDetail();
                      setShowDropdown(false);
                    }}
                    className="w-full text-left px-4 py-2 text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                  >
                    {t('viewDetail') || 'View Detail'}
                  </button>
                )}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    navigator.clipboard.writeText(execution.executionId);
                    setShowDropdown(false);
                  }}
                  className="w-full text-left px-4 py-2 text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                >
                  {t('copyId') || 'Copy ID'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

