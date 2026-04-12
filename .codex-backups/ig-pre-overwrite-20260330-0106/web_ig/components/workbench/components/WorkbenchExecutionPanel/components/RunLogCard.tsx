/**
 * Individual run log card component
 */
import React from 'react';
import { Loader2 } from 'lucide-react';
import type { RunInfo } from '../types';
import { formatRelativeTime } from '../utils/formatters';
import { getRunPrimarySubject } from '../utils';

interface RunLogCardProps {
    workspaceId: string;
    run: RunInfo;
    index: number;
    rerunBusyId: string | null;
    igRerunAllowPartial: boolean;
    canRerunStatus: (status: any) => boolean;
    rerunExecution: (executionId: string, overrideInputs?: Record<string, any>) => Promise<void>;
}

export function RunLogCard({
    workspaceId,
    run,
    index,
    rerunBusyId,
    igRerunAllowPartial,
    canRerunStatus,
    rerunExecution,
}: RunLogCardProps) {
    const executionId = run.execution_id || run.id || '';
    const primarySubject = getRunPrimarySubject(run);

    return (
        <div
            key={run.id || `run-${index}`}
            className="group relative bg-white dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/50 p-2.5 text-xs transition-colors"
        >
            <div className="flex flex-col gap-1.5">
                {/* Row 1: Title and Time */}
                <div className="flex items-start justify-between gap-2">
                    <div className="flex flex-col gap-1 min-w-0">
                        <span className="font-semibold text-gray-900 dark:text-gray-100 truncate flex items-center gap-1.5">
                            <span className="uppercase tracking-wider">
                                {(run.playbook_code || '').replace('ig_', '').replace(/_/g, ' ')}
                            </span>
                        </span>
                        {primarySubject && (
                            <span className="text-[10.5px] text-gray-500 dark:text-gray-400 font-mono font-normal break-all">
                                {primarySubject.value}
                            </span>
                        )}
                        {executionId && (
                            <span
                                className="text-[9px] text-gray-400 dark:text-gray-500 font-mono cursor-pointer hover:text-gray-600 dark:hover:text-gray-300 truncate"
                                title={`Click to copy: ${executionId}`}
                                onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(executionId); }}
                            >
                                {executionId.slice(0, 8)}…
                            </span>
                        )}
                    </div>
                    {run.created_at && (
                        <div className="text-gray-400 dark:text-gray-500 text-[10px] whitespace-nowrap shrink-0 mt-0.5">
                            {formatRelativeTime(run.created_at)}
                        </div>
                    )}
                </div>

                {/* Row 2: Status Pill and Actions */}
                <div className="flex items-center justify-between">
                    <span
                        className={`shrink-0 px-2 py-0.5 rounded-[4px] text-[10px] font-bold tracking-wider uppercase flex items-center gap-1.5 ${
                            run.status === 'completed'
                                ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 border border-green-200 dark:border-green-800/50'
                                : run.status === 'failed'
                                    ? 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400 border border-red-200 dark:border-red-800/50'
                                    : ['pending', 'queued'].includes((run.status || '').toLowerCase())
                                        ? 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400 border border-amber-200 dark:border-amber-800/50'
                                        : 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400 border border-blue-200 dark:border-blue-800/50'
                        }`}
                    >
                        {['running', 'queued', 'pending', 'paused'].includes((run.status || '').toLowerCase()) && (
                            <Loader2 className="w-3 h-3 animate-spin opacity-70" />
                        )}
                        {run.status || 'unknown'}
                    </span>

                    {/* Hover Actions (Rerun) */}
                    <div className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1">
                        {canRerunStatus(run.status) && executionId && (
                            <>
                                {run.playbook_code !== 'ig_analyze_following' ? (
                                    <button
                                        onClick={() => rerunExecution(executionId)}
                                        disabled={rerunBusyId === executionId}
                                        className="px-2 py-1 text-[10px] rounded bg-white hover:bg-gray-50 dark:bg-gray-800 dark:hover:bg-gray-700 border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300"
                                    >
                                        Rerun
                                    </button>
                                ) : (
                                    <>
                                        <button
                                            onClick={() => rerunExecution(executionId, { run_mode: 'list', visit_account_pages: false })}
                                            disabled={rerunBusyId === executionId}
                                            className="px-2 py-1 text-[10px] rounded bg-white hover:bg-gray-50 dark:bg-gray-800 dark:hover:bg-gray-700 border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300"
                                        >
                                            List
                                        </button>
                                        <button
                                            onClick={() => rerunExecution(executionId, { run_mode: 'visit', visit_account_pages: true, allow_partial_resume: igRerunAllowPartial })}
                                            disabled={rerunBusyId === executionId}
                                            className="px-2 py-1 text-[10px] rounded bg-white hover:bg-gray-50 dark:bg-gray-800 dark:hover:bg-gray-700 border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300"
                                        >
                                            Visit
                                        </button>
                                    </>
                                )}
                            </>
                        )}
                    </div>
                </div>
            </div>

            {/* Error Message (only when expanded/hovered conceptually, but let's keep it visible if failed) */}
            {run.status === 'failed' && (run.task?.error || run.failure_reason) && (
                <div className="mt-1.5 text-[10px] text-red-600 dark:text-red-400 leading-snug break-words opacity-80">
                    {(run.task?.error || run.failure_reason || '').toString()}
                </div>
            )}
        </div>
    );
}
