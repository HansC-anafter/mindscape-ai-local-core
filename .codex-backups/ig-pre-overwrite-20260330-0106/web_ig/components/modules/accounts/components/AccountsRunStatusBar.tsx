import React, { useMemo, useState } from 'react';
import { AlertCircle, ChevronDown, ChevronUp, Copy, Loader2, X } from 'lucide-react';
import { parseServerTimestamp as parseTimestamp, formatLocalTime, minutesAgo } from '@/lib/time';

import type { AccountsRunStatus } from '../hooks/useAccountsRunStatus';

function shortId(id: string) {
  if (!id) return '';
  return id.length > 8 ? `${id.slice(0, 8)}…` : id;
}

export function AccountsRunStatusBar(props: {
  runStatus: AccountsRunStatus;
  onDismiss: () => void;
  onOpen?: () => void;
}) {
  const { runStatus, onDismiss, onOpen } = props;
  const status = (runStatus.status || '').toLowerCase();
  const isRunning = status === 'running' || status === 'queued' || status === 'paused';
  const [expanded, setExpanded] = useState(false);

  const progressAgeMinutes = useMemo(() => {
    const m = minutesAgo(runStatus.progress?.updated_at);
    return typeof m === 'number' ? m : null;
  }, [runStatus.progress?.updated_at]);

  const isProgressStale = useMemo(() => {
    if (!isRunning) return false;
    if (progressAgeMinutes === null) return true;
    return progressAgeMinutes >= 5;
  }, [isRunning, progressAgeMinutes]);

  const label = useMemo(() => {
    const parts: string[] = [];
    parts.push(runStatus.playbook_code);
    parts.push(isRunning ? 'running' : runStatus.status || 'unknown');

    const backend = (runStatus.execution_backend_hint || '').toString().trim();
    if (backend) parts.push(`backend=${backend}`);

    const stage = runStatus.progress?.stage;
    if (stage) parts.push(stage);

    if (
      typeof runStatus.progress?.page_total === 'number' &&
      typeof runStatus.progress?.page_index === 'number' &&
      runStatus.progress.page_total > 0
    ) {
      parts.push(`${Math.min(runStatus.progress.page_index + 1, runStatus.progress.page_total)}/${runStatus.progress.page_total}`);
    }

    const total = runStatus.progress?.total_accounts;
    if (typeof total === 'number') parts.push(`${total} targets`);

    if (isProgressStale) {
      parts.push(progressAgeMinutes === null ? 'stale' : `stale ${progressAgeMinutes}m`);
    }

    const err = runStatus.progress?.error_type;
    if (err && err !== 'unknown') parts.push(err);

    return parts.join(' · ');
  }, [runStatus, isRunning, isProgressStale, progressAgeMinutes]);

  const openLabel = useMemo(() => {
    if (runStatus.playbook_code === 'ig_analyze_following') return 'Targets';
    if (runStatus.playbook_code === 'ig_capture_account_snapshot') return 'Captures';
    return 'Open';
  }, [runStatus.playbook_code]);

  const copyExecutionId = async () => {
    try {
      await navigator.clipboard.writeText(runStatus.execution_id);
    } catch {
    }
  };

  return (
    <div className="min-w-0">
      <div className={`min-w-0 flex items-center justify-between gap-2 px-2 py-1.5 rounded-md border ${
        isProgressStale
          ? 'bg-amber-50 dark:bg-amber-900/10 border-amber-200 dark:border-amber-800'
          : 'bg-gray-50 dark:bg-gray-800/60 border-gray-200 dark:border-gray-700'
      }`}>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="min-w-0 flex items-center gap-2 text-left"
          title={label}
        >
        {isRunning ? (
          <Loader2 className={`w-4 h-4 animate-spin shrink-0 ${
            isProgressStale ? 'text-amber-700 dark:text-amber-300' : 'text-blue-600 dark:text-blue-400'
          }`} />
        ) : (
          <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
        )}
        <div className="min-w-0">
          <div className="text-xs text-gray-900 dark:text-gray-100 whitespace-nowrap overflow-hidden text-ellipsis">
            {label}
          </div>
          <div className="text-[11px] text-gray-500 dark:text-gray-400 whitespace-nowrap overflow-hidden text-ellipsis">
            exec {shortId(runStatus.execution_id)}
            {runStatus.progress?.updated_at ? ` · last update ${formatLocalTime(runStatus.progress.updated_at)}` : ' · no progress timestamp'}
            {isProgressStale && progressAgeMinutes !== null ? ` · ${progressAgeMinutes}m ago` : ''}
          </div>
        </div>
        </button>

        <div className="flex items-center gap-1 shrink-0">
          {onOpen && (
            <button
              onClick={onOpen}
              className="px-2 py-1 text-[11px] rounded bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200"
              title={openLabel}
            >
              {openLabel}
            </button>
          )}
        <button
          onClick={copyExecutionId}
          className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
          title="Copy execution id"
        >
          <Copy className="w-3.5 h-3.5 text-gray-600 dark:text-gray-300" />
        </button>
        <button
          onClick={() => setExpanded((v) => !v)}
          className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
          title={expanded ? 'Collapse' : 'Expand'}
        >
          {expanded ? (
            <ChevronUp className="w-3.5 h-3.5 text-gray-600 dark:text-gray-300" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5 text-gray-600 dark:text-gray-300" />
          )}
        </button>
        <button
          onClick={onDismiss}
          className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
          title="Dismiss"
        >
          <X className="w-3.5 h-3.5 text-gray-600 dark:text-gray-300" />
        </button>
      </div>
    </div>

      {expanded && (
        <div className="mt-1 px-2 py-1.5 rounded-md bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-[11px] text-gray-700 dark:text-gray-200">
          {isProgressStale && (
            <div className="mb-2 rounded border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/10 px-2 py-1 text-amber-800 dark:text-amber-200">
              Progress is stale. The run may still be executing, but this UI has no newer progress events.
            </div>
          )}
          <div className="flex flex-wrap gap-x-3 gap-y-1">
            {runStatus.execution_backend_hint && (
              <div>
                <span className="text-gray-500">backend</span> {runStatus.execution_backend_hint}
              </div>
            )}
            {runStatus.progress?.stage && <div><span className="text-gray-500">stage</span> {runStatus.progress.stage}</div>}
            {runStatus.progress?.updated_at && (
              <div>
                <span className="text-gray-500">last_update</span>{' '}
                {formatLocalTime(runStatus.progress.updated_at)}
                {typeof minutesAgo(runStatus.progress.updated_at) === 'number' ? ` (${minutesAgo(runStatus.progress.updated_at)}m ago)` : ''}
              </div>
            )}
            {typeof runStatus.progress?.iteration === 'number' && <div><span className="text-gray-500">iter</span> {runStatus.progress.iteration}</div>}
            {typeof runStatus.progress?.total_accounts === 'number' && <div><span className="text-gray-500">targets</span> {runStatus.progress.total_accounts}</div>}
            {typeof runStatus.progress?.page_index === 'number' && typeof runStatus.progress?.page_total === 'number' && (
              <div>
                <span className="text-gray-500">pages</span>{' '}
                {Math.min(runStatus.progress.page_index + 1, runStatus.progress.page_total)}/{runStatus.progress.page_total}
              </div>
            )}
            {runStatus.progress?.current_account && (
              <div className="truncate max-w-[220px]">
                <span className="text-gray-500">current</span> {runStatus.progress.current_account}
              </div>
            )}
            {typeof runStatus.progress?.no_change_count === 'number' && <div><span className="text-gray-500">no_change</span> {runStatus.progress.no_change_count}</div>}
            {typeof runStatus.progress?.reached_bottom === 'boolean' && <div><span className="text-gray-500">bottom</span> {runStatus.progress.reached_bottom ? 'yes' : 'no'}</div>}
            {runStatus.progress?.error_type && <div><span className="text-gray-500">error</span> {runStatus.progress.error_type}</div>}
          </div>
          {(runStatus.progress?.error_message || runStatus.task_error || runStatus.failure_reason) && (
            <div className="mt-1 text-amber-700 dark:text-amber-300 break-words">
              {(runStatus.progress?.error_message || runStatus.task_error || runStatus.failure_reason || '').toString()}
            </div>
          )}
          <div className="mt-1 text-gray-500 break-all">execution_id {runStatus.execution_id}</div>
        </div>
      )}
    </div>
  );
}
