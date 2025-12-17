'use client';

/**
 * WebGenerationContextBar - Context bar for displaying baseline status and actions
 *
 * Displays baseline status, snapshot info, and action buttons based on current state.
 * Uses the useBaselineStatus hook for state management.
 */

import React from 'react';
import { useBaselineStatus, BaselineStatus } from '@/hooks/useBaselineStatus';

interface WebGenerationContextBarProps {
  workspaceId: string;
  projectId?: string;
  onImport?: () => void;
  onDiff?: () => void;
  onReview?: () => void;
}

export function WebGenerationContextBar({
  workspaceId,
  projectId,
  onImport,
  onDiff,
  onReview,
}: WebGenerationContextBarProps) {
  const {
    status,
    context,
    isLoading,
    error,
    setBaseline,
    unlock,
    sync,
  } = useBaselineStatus(workspaceId, projectId);

  // Handle set baseline
  const handleSetBaseline = async () => {
    if (!context || !context.snapshotId) {
      // If no snapshot selected, trigger import
      onImport?.();
      return;
    }

    // Use first available snapshot if none is set
    // This is a fallback - ideally user should select a snapshot first
    try {
      await setBaseline(context.snapshotId, context.variantId, false);
    } catch (err) {
      console.error('Failed to set baseline:', err);
    }
  };

  // Handle lock
  const handleLock = async () => {
    if (!context?.snapshotId) return;
    try {
      await setBaseline(context.snapshotId, context.variantId, true);
    } catch (err) {
      console.error('Failed to lock baseline:', err);
    }
  };

  // Handle unlock
  const handleUnlock = async () => {
    try {
      await unlock();
    } catch (err) {
      console.error('Failed to unlock baseline:', err);
    }
  };

  // Handle re-sync
  const handleReSync = async () => {
    try {
      await sync('Re-synced by user');
    } catch (err) {
      console.error('Failed to re-sync baseline:', err);
    }
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-6 py-3">
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <div className="w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
          Loading baseline status...
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="bg-red-50 dark:bg-red-900/20 border-b border-red-200 dark:border-red-800 px-6 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
            <span>⚠️</span>
            <span>Error: {error}</span>
          </div>
          <button
            onClick={() => window.location.reload()}
            className="px-3 py-1 text-xs bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300 rounded hover:bg-red-200 dark:hover:bg-red-800 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-6 py-3">
      <div className="flex items-center justify-between">
        {/* Left: Status & Info */}
        <div className="flex items-center gap-4">
          {/* Baseline Badge */}
          <BaselineStatusBadge status={status} />

          {/* Snapshot Info */}
          {status !== 'absent' && context && (
            <div className="flex items-center gap-3 text-sm">
              <span className="text-gray-700 dark:text-gray-300">
                Snapshot:{' '}
                <span className="font-mono font-semibold">v{context.snapshotVersion || 'unknown'}</span>
              </span>
              {context.variantId && (
                <>
                  <span className="text-gray-400">•</span>
                  <span className="text-gray-700 dark:text-gray-300">
                    Variant: <span className="font-semibold">{context.variantId}</span>
                  </span>
                </>
              )}
            </div>
          )}

          {/* Bound To Info */}
          {context?.boundSpecVersion && (
            <div className="text-xs text-gray-500 dark:text-gray-400">
              Bound to: Spec v{context.boundSpecVersion}
              {context.boundOutlineVersion && ` / Outline v${context.boundOutlineVersion}`}
            </div>
          )}

          {/* Stale Warning */}
          {status === 'stale' && context?.staleInfo && (
            <div className="text-xs text-orange-600 dark:text-orange-400">
              ⚠️ {context.staleInfo.reason || 'Baseline is outdated'}
            </div>
          )}
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-2">
          {status === 'absent' && (
            <button
              onClick={() => onImport?.()}
              className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
            >
              <span>📥</span>
              Import Baseline
            </button>
          )}

          {status === 'present-not-applied' && (
            <button
              onClick={handleSetBaseline}
              className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors"
            >
              Set as Baseline
            </button>
          )}

          {status === 'applied-unlocked' && (
            <>
              <button
                onClick={handleLock}
                className="px-4 py-2 border border-gray-300 dark:border-gray-600 text-sm rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors flex items-center gap-2"
              >
                <span>🔒</span>
                Lock
              </button>
              <button
                onClick={() => onDiff?.()}
                className="px-4 py-2 border border-gray-300 dark:border-gray-600 text-sm rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors flex items-center gap-2"
              >
                <span>🔀</span>
                Diff
              </button>
            </>
          )}

          {status === 'applied-locked' && (
            <>
              <button
                onClick={handleUnlock}
                className="px-4 py-2 border border-gray-300 dark:border-gray-600 text-sm rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors flex items-center gap-2"
              >
                <span>🔓</span>
                Unlock
              </button>
              <button
                onClick={() => onDiff?.()}
                className="px-4 py-2 border border-gray-300 dark:border-gray-600 text-sm rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors flex items-center gap-2"
              >
                <span>🔀</span>
                Diff
              </button>
            </>
          )}

          {status === 'stale' && (
            <>
              <button
                onClick={handleReSync}
                className="px-4 py-2 bg-orange-600 text-white text-sm rounded-lg hover:bg-orange-700 transition-colors flex items-center gap-2"
              >
                <span>🔄</span>
                Re-sync
              </button>
              <button
                onClick={() => onReview?.()}
                className="px-4 py-2 border border-gray-300 dark:border-gray-600 text-sm rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
              >
                Review Changes
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// BaselineStatusBadge Component
// ============================================================================

function BaselineStatusBadge({ status }: { status: BaselineStatus }) {
  const config: Record<
    BaselineStatus,
    { label: string; className: string; icon: string }
  > = {
    absent: {
      label: 'No Baseline',
      className: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
      icon: '○',
    },
    'present-not-applied': {
      label: 'Available',
      className: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
      icon: '✓',
    },
    'applied-unlocked': {
      label: 'Applied',
      className: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
      icon: '✓',
    },
    'applied-locked': {
      label: 'Locked',
      className: 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300',
      icon: '🔒',
    },
    stale: {
      label: 'Stale',
      className: 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300',
      icon: '⚠️',
    },
    error: {
      label: 'Error',
      className: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
      icon: '✗',
    },
  };

  const { label, className, icon } = config[status];

  return (
    <div
      className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium ${className}`}
    >
      <span>{icon}</span>
      <span>{label}</span>
    </div>
  );
}
