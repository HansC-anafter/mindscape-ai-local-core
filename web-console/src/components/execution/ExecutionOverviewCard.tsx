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
    queued: t('queued' as any) || 'Queued',
    running: t('running' as any) || 'Running',
    paused: t('paused' as any) || 'Paused',
    completed: t('completed' as any) || 'Completed',
    failed: t('failed' as any) || 'Failed'
  };

  const getPrimaryAction = () => {
    switch (execution.status) {
      case 'paused':
        return {
          label: t('confirmContinue' as any) || 'Confirm Continue',
          onClick: onConfirm,
          className: 'bg-accent dark:bg-blue-600 hover:bg-accent/90 dark:hover:bg-blue-700 text-white'
        };
      case 'running':
        return {
          label: t('viewDetail' as any) || 'View Detail',
          onClick: onViewDetail || onFocus,
          className: 'bg-accent dark:bg-blue-600 hover:bg-accent/90 dark:hover:bg-blue-700 text-white'
        };
      case 'completed':
        return {
          label: t('viewResult' as any) || 'View Result',
          onClick: onViewDetail || onFocus,
          className: 'bg-green-600 hover:bg-green-700 text-white'
        };
      case 'failed':
        return {
          label: t('retry' as any) || 'Retry',
          onClick: onRetry,
          className: 'bg-accent dark:bg-blue-600 hover:bg-accent/90 dark:hover:bg-blue-700 text-white'
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
          ? 'bg-accent-10 dark:bg-blue-900/20 border-accent dark:border-blue-700'
          : 'bg-surface-accent dark:bg-gray-900 border-default dark:border-gray-700 hover:border-default dark:hover:border-gray-600'
      }`}
      onClick={onFocus}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-primary dark:text-gray-100">
            Execution #{execution.runNumber}
          </span>
          <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${
            execution.status === 'running'
              ? 'bg-accent-10 dark:bg-blue-900/30 text-accent dark:text-blue-300'
              : execution.status === 'paused'
              ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300'
              : execution.status === 'completed'
              ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
              : execution.status === 'failed'
              ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
              : 'bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-300'
          }`}>
            {statusLabels[execution.status]}
          </span>
        </div>
      </div>

      <div className="mb-2">
        <div className="text-xs text-secondary dark:text-gray-400 mb-1">
          Step {execution.currentStep.index}: {execution.currentStep.name}
        </div>
        <div className="h-1.5 bg-default dark:bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-accent dark:bg-blue-400 transition-all"
            style={{ width: `${progressPercentage}%` }}
          />
        </div>
        <div className="text-xs text-secondary dark:text-gray-500 mt-1">
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
            className="px-2 py-1.5 text-xs font-medium text-primary dark:text-gray-300 bg-surface-secondary dark:bg-gray-800 rounded-md hover:bg-surface-accent dark:hover:bg-gray-700 transition-colors"
          >
            ⋯
          </button>

          {showDropdown && (
            <div className="absolute right-0 mt-1 w-48 bg-surface-accent dark:bg-gray-800 border border-default dark:border-gray-700 rounded-md shadow-lg z-10">
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
                    {t('reject' as any) || 'Reject'}
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
                        className="w-full text-left px-4 py-2 text-xs text-primary dark:text-gray-300 hover:bg-surface-secondary dark:hover:bg-gray-700"
                      >
                        {t('pause' as any) || 'Pause'}
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
                        {t('cancel' as any) || 'Cancel'}
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
                    className="w-full text-left px-4 py-2 text-xs text-primary dark:text-gray-300 hover:bg-surface-secondary dark:hover:bg-gray-700"
                  >
                    {t('viewDetail' as any) || 'View Detail'}
                  </button>
                )}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    navigator.clipboard.writeText(execution.executionId);
                    setShowDropdown(false);
                  }}
                  className="w-full text-left px-4 py-2 text-xs text-gray-700 dark:text-gray-300 hover:bg-tertiary dark:hover:bg-gray-700"
                >
                  {t('copyId' as any) || 'Copy ID'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

