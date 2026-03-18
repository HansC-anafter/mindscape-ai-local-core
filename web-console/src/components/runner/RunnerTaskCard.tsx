'use client';

/**
 * RunnerTaskCard — Universal debug card for all runner-executed tasks.
 *
 * Displays: status badge, queue position, dependency hold warning,
 * heartbeat age, step progress (if available), error, exec ID copy.
 *
 * Accepts an `extensionSlot` for capability-specific content (e.g. IG scroll/visit).
 */
import React, { ReactNode } from 'react';
import { Loader2, AlertTriangle, Clock, Hash, Wifi, WifiOff } from 'lucide-react';

export interface RunnerTaskCardProps {
  /** Task status */
  status: string;
  /** Playbook code (e.g. ig_analyze_pinned_reference) */
  playbookCode?: string;
  /** Queue position (1-based) */
  queuePosition?: number | null;
  /** Total tasks in queue */
  queueTotal?: number | null;
  /** Dependency hold info */
  dependencyHold?: { deps: string[]; checked_at: string } | null;
  /** Heartbeat timestamp (ISO) */
  heartbeatAt?: string | null;
  /** Runner ID */
  runnerId?: string | null;
  /** SSE connected */
  isConnected?: boolean;
  /** Step progress from execution_context */
  progress?: {
    current_step_index?: number;
    total_steps?: number;
    current_step_name?: string;
    [key: string]: any;
  } | null;
  /** Execution ID */
  executionId?: string;
  /** Error message */
  error?: string | null;
  /** Created at timestamp */
  createdAt?: string | null;
  /** Capability-specific extension content */
  extensionSlot?: ReactNode;
}

function formatAge(isoStr: string | null | undefined): string {
  if (!isoStr) return '—';
  const diffMs = Date.now() - new Date(isoStr).getTime();
  if (diffMs < 0) return 'just now';
  const secs = Math.floor(diffMs / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m ago`;
}

function isStale(isoStr: string | null | undefined, thresholdMs = 60_000): boolean {
  if (!isoStr) return false;
  return Date.now() - new Date(isoStr).getTime() > thresholdMs;
}

const STATUS_STYLES: Record<string, string> = {
  pending: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400 border-amber-200 dark:border-amber-800/50',
  running: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400 border-blue-200 dark:border-blue-800/50',
  completed: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 border-green-200 dark:border-green-800/50',
  succeeded: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 border-green-200 dark:border-green-800/50',
  failed: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400 border-red-200 dark:border-red-800/50',
  cancelled: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400 border-gray-200 dark:border-gray-700',
};

export function RunnerTaskCard({
  status,
  playbookCode,
  queuePosition,
  queueTotal,
  dependencyHold,
  heartbeatAt,
  runnerId,
  isConnected,
  progress,
  executionId,
  error,
  createdAt,
  extensionSlot,
}: RunnerTaskCardProps) {
  const statusLower = (status || 'unknown').toLowerCase();
  const isPending = statusLower === 'pending';
  const isRunning = statusLower === 'running';
  const isFailed = statusLower === 'failed';
  const statusStyle = STATUS_STYLES[statusLower] || STATUS_STYLES.pending;

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-3 text-xs space-y-2">
      {/* Header: playbook + status */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          {playbookCode && (
            <span className="font-semibold text-gray-900 dark:text-gray-100 uppercase tracking-wider truncate">
              {playbookCode.replace(/^ig_/, '').replace(/_/g, ' ')}
            </span>
          )}
          <span className={`shrink-0 px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase border flex items-center gap-1 ${statusStyle}`}>
            {(isPending || isRunning) && <Loader2 className="w-3 h-3 animate-spin opacity-70" />}
            {statusLower}
          </span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {isConnected !== undefined && (
            isConnected
              ? <Wifi className="w-3 h-3 text-green-500" />
              : <WifiOff className="w-3 h-3 text-gray-400" />
          )}
          {createdAt && (
            <span className="text-[10px] text-gray-400">{formatAge(createdAt)}</span>
          )}
        </div>
      </div>

      {/* Queue position (pending only) */}
      {isPending && queuePosition != null && queueTotal != null && (
        <div className="flex items-center gap-1.5 text-amber-700 dark:text-amber-400">
          <Hash className="w-3 h-3" />
          <span className="font-mono font-semibold">#{queuePosition} / {queueTotal}</span>
          <span className="text-gray-500 dark:text-gray-400 ml-1">in queue</span>
        </div>
      )}

      {/* Dependency hold warning */}
      {dependencyHold && (
        <div className="flex items-start gap-1.5 px-2 py-1.5 rounded border bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800/50 text-amber-700 dark:text-amber-400">
          <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          <div>
            <span className="font-semibold">Waiting for:</span>{' '}
            {dependencyHold.deps.join(', ')}
            <div className="text-[10px] opacity-70 mt-0.5">
              Queued (last evaluated {formatAge(dependencyHold.checked_at)})
            </div>
          </div>
        </div>
      )}

      {/* Step progress (if available) */}
      {isRunning && progress && progress.total_steps != null && (
        <div className="space-y-1">
          <div className="flex items-center justify-between text-[10px]">
            <span className="text-gray-600 dark:text-gray-400 truncate">
              {progress.current_step_name || `Step ${(progress.current_step_index ?? 0) + 1}`}
            </span>
            <span className="font-mono text-gray-500">
              {(progress.current_step_index ?? 0) + 1}/{progress.total_steps}
            </span>
          </div>
          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1">
            <div
              className="bg-blue-500 h-1 rounded-full transition-all duration-300"
              style={{ width: `${Math.min(100, (((progress.current_step_index ?? 0) + 1) / progress.total_steps) * 100)}%` }}
            />
          </div>
        </div>
      )}

      {/* Heartbeat (running only) */}
      {isRunning && heartbeatAt && (
        <div className="flex items-center gap-1.5 text-[10px] text-gray-500 dark:text-gray-400">
          <Clock className="w-3 h-3" />
          <span>Heartbeat: {formatAge(heartbeatAt)}</span>
          {runnerId && <span className="font-mono">· {runnerId.slice(0, 8)}</span>}
        </div>
      )}

      {/* Extension slot */}
      {extensionSlot}

      {/* Error */}
      {isFailed && error && (
        <div className="text-[10px] text-red-600 dark:text-red-400 leading-snug break-words bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-800/50 rounded px-2 py-1.5">
          {error}
        </div>
      )}

      {/* Exec ID */}
      {executionId && (
        <div className="flex items-center justify-end">
          <span
            className="text-[9px] text-gray-400 dark:text-gray-500 font-mono cursor-pointer hover:text-gray-600 dark:hover:text-gray-300"
            title={`Click to copy: ${executionId}`}
            onClick={() => navigator.clipboard.writeText(executionId)}
          >
            {executionId.slice(0, 8)}…
          </span>
        </div>
      )}
    </div>
  );
}
