/**
 * SeedExecutionBar — Inline progress widget for a seed's active execution.
 *
 * Shows a compact status badge + progress bar inside the SeedCard header area.
 */
import React from 'react';
import { Loader2, Clock, CheckCircle2, XCircle } from 'lucide-react';

export interface IGDebugInfo {
    executionId: string;
    updatedAt: string | null;
    stage: string | null;
    iter: number | null;
    targets: number | null;
    expectedFollowing: number | null;
    stopReason: string | null;
    savedDedupTargets: number | null;
    visitedCount: number | null;
    pageIndex: number | null;
    pageTotal: number | null;
    currentAccount: string | null;
    noChangeCount: number | null;
    noNewAccountsStreak: number | null;
    reachedBottom: boolean | null;
    errorType: string | null;
    errorMessage: string | null;
    scrollMode: string | null;
    runMode: string | null;
    executionBackendHint: string | null;
    visitAccountPages: boolean | null;
    listCaptureStatus: string | null;
    allowPartialResume: boolean | null;
    screenshots: string[];
}

export interface SeedExecutionBarProps {
    status: 'running' | 'pending' | 'completed' | 'failed' | 'idle';
    queuePosition?: number;
    debug: IGDebugInfo | null;
    blockedReason?: string | null;
    errorMessage?: string | null;
}

function formatPendingLabel(queuePosition?: number, blockedReason?: string | null): string {
    const reason = (blockedReason || '').trim().toLowerCase();
    if (reason === 'refreshing') return 'Refreshing…';
    if (reason === 'concurrency_locked') return 'Waiting for session slot';
    if (reason === 'dependency_hold') return 'Waiting for dependencies';
    if (reason) return 'Waiting to resume';
    return `Pending${queuePosition ? ` · #${queuePosition} in queue` : ''}`;
}

export function SeedExecutionBar({ status, queuePosition, debug, blockedReason, errorMessage }: SeedExecutionBarProps) {
    if (status === 'idle') return null;

    return (
        <div className="mt-2">
            {status === 'running' && debug && (
                <RunningBar debug={debug} />
            )}
            {status === 'running' && !debug && (
                <div className="flex items-center gap-1.5 text-xs text-blue-600 dark:text-blue-400">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    <span>Running…</span>
                </div>
            )}
            {status === 'pending' && (
                <div className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400">
                    <Clock className="w-3 h-3" />
                    <span>{formatPendingLabel(queuePosition, blockedReason)}</span>
                </div>
            )}
            {status === 'completed' && (
                <div className="flex items-center gap-1.5 text-xs text-green-600 dark:text-green-400">
                    <CheckCircle2 className="w-3 h-3" />
                    <span>Completed</span>
                </div>
            )}
            {status === 'failed' && (
                <div className="text-xs">
                    <div className="flex items-center gap-1.5 text-red-600 dark:text-red-400">
                        <XCircle className="w-3 h-3" />
                        <span>Failed</span>
                    </div>
                    {errorMessage && (
                        <div className="mt-1 text-[10px] text-red-500 dark:text-red-400 break-words whitespace-pre-wrap" title={errorMessage}>
                            {errorMessage}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

/** Running state with progress bars */
function RunningBar({ debug }: { debug: IGDebugInfo }) {
    const stage = debug.stage || 'starting';
    const saved = debug.savedDedupTargets ?? debug.targets ?? 0;
    const expected = debug.expectedFollowing ?? 0;

    // Scroll progress
    const scrollPct = expected > 0 ? Math.min(100, Math.round((saved / expected) * 100)) : 0;

    // Visit progress
    const visited = debug.visitedCount ?? 0;
    const visitTotal = debug.pageTotal ?? debug.targets ?? 0;
    const visitPct = visitTotal > 0 ? Math.min(100, Math.round((visited / visitTotal) * 100)) : 0;

    const isVisiting = stage === 'visiting_pages' || stage === 'visit_pages';

    return (
        <div className="space-y-1.5">
            {/* Stage + iterator */}
            <div className="flex items-center gap-1.5 text-xs text-blue-600 dark:text-blue-400">
                <Loader2 className="w-3 h-3 animate-spin flex-shrink-0" />
                <span className="font-medium">{stage}</span>
                {debug.iter != null && <span className="text-gray-400">· iter {debug.iter}</span>}
                {isVisiting && debug.currentAccount && (
                    <span className="text-gray-400 truncate max-w-[100px]">· @{debug.currentAccount}</span>
                )}
            </div>

            {/* Scroll progress bar */}
            <div>
                <div className="flex items-center justify-between text-[10px] text-gray-500 dark:text-gray-400 mb-0.5">
                    <span>{scrollPct}% saved</span>
                    <span>{saved}/{expected}</span>
                </div>
                <div className="w-full h-1.5 bg-gray-200 dark:bg-gray-600 rounded-full overflow-hidden">
                    <div
                        className="h-full bg-blue-500 rounded-full transition-all duration-300"
                        style={{ width: `${scrollPct}%` }}
                    />
                </div>
            </div>

            {/* Visit progress bar (only if visiting or visit data exists) */}
            {(isVisiting || visited > 0) && (
                <div>
                    <div className="flex items-center justify-between text-[10px] text-gray-500 dark:text-gray-400 mb-0.5">
                        <span>{visitPct}% visited</span>
                        <span>{visited}/{visitTotal}</span>
                    </div>
                    <div className="w-full h-1.5 bg-gray-200 dark:bg-gray-600 rounded-full overflow-hidden">
                        <div
                            className="h-full bg-purple-500 rounded-full transition-all duration-300"
                            style={{ width: `${visitPct}%` }}
                        />
                    </div>
                </div>
            )}
        </div>
    );
}
