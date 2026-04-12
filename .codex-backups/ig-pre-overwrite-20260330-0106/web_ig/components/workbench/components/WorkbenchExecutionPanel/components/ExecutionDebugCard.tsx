/**
 * Execution Debug Card for IG Following Analyzer
 */
import React from 'react';
import {
    AlertCircle,
    ChevronDown,
    ChevronUp,
    Copy,
    Loader2,
    Skull,
    Wifi,
    WifiOff,
    X,
} from 'lucide-react';
import type { RunInfo, IGDebugInfo, ForcedExecution } from '../types';
import { formatRelativeTime, minutesAgo } from '../utils/formatters';
import { getRunDetailItems, supportsIGAnalyzerDebug } from '../utils';

import { useRunnerTaskDebug } from '@/hooks/useRunnerTaskDebug';
import { RunnerTaskCard } from '@/components/runner/RunnerTaskCard';

interface ExecutionDebugCardProps {
    workspaceId: string;
    apiUrl: string;
    igExecutionId: string | null;
    igPinnedRun: RunInfo | null;
    latestIGRun: RunInfo | null;
    forcedExecution: ForcedExecution | null;
    igDebug: IGDebugInfo | null;
    igDebugLoading: boolean;
    igDebugError: string | null;
    igDebugExpanded: boolean;
    igRerunAllowPartial: boolean;

    setIgDebugExpanded: (expanded: boolean) => void;
    setIgRerunAllowPartial: (value: boolean) => void;
    fetchLatestIGDebug: (showLoading?: boolean) => Promise<void>;
    copyExecutionId: () => Promise<void>;
    screenshotUrl: (executionId: string, fullPath: string) => string;
    cancelExecution: (executionId: string) => Promise<void>;
    rerunExecution: (executionId: string, overrideInputs?: Record<string, any>) => Promise<void>;
    canRerunStatus: (status: any) => boolean;

    cancelBusyId: string | null;
    rerunBusyId: string | null;
    enableRunnerDebugTransport?: boolean;
}

const STATUS_STYLES: Record<string, string> = {
    pending: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400 border-amber-200 dark:border-amber-800/50',
    running: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400 border-blue-200 dark:border-blue-800/50',
    completed: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 border-green-200 dark:border-green-800/50',
    succeeded: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 border-green-200 dark:border-green-800/50',
    failed: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400 border-red-200 dark:border-red-800/50',
    cancelled: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400 border-gray-200 dark:border-gray-700',
};

function formatTaskTitle(playbookCode: string): string {
    const raw = (playbookCode || '').toString().trim();
    if (!raw) return 'Task';
    return raw
        .replace(/^ig_/, '')
        .split('_')
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ');
}

function getProfileSessionName(profilePath: string | null | undefined): string | null {
    const raw = (profilePath || '').toString().trim();
    if (!raw) return null;
    const parts = raw.split('/').filter(Boolean);
    return parts.length > 0 ? parts[parts.length - 1] : raw;
}

export function ExecutionDebugCard({
    workspaceId,
    apiUrl,
    igExecutionId,
    igPinnedRun,
    latestIGRun,
    forcedExecution,
    igDebug,
    igDebugLoading,
    igDebugError,
    igDebugExpanded,
    igRerunAllowPartial,
    setIgDebugExpanded,
    setIgRerunAllowPartial,
    fetchLatestIGDebug,
    copyExecutionId,
    screenshotUrl,
    cancelExecution,
    rerunExecution,
    canRerunStatus,
    cancelBusyId,
    rerunBusyId,
    enableRunnerDebugTransport = true,
}: ExecutionDebugCardProps) {
    const status = (igPinnedRun?.status || '').toString().toLowerCase();
    const shouldShow = (!!igExecutionId || !!igPinnedRun) && status !== 'pending';

    const runnerDebug = useRunnerTaskDebug(
        enableRunnerDebugTransport ? igExecutionId : null,
        workspaceId,
        apiUrl
    );

    if (!shouldShow) return null;

    const playbookCode = (igPinnedRun?.playbook_code || '').toString();
    const supportsIGDebug = supportsIGAnalyzerDebug(playbookCode);
    const runDetailItems = getRunDetailItems(igPinnedRun);
    const seed = igPinnedRun?.execution_context?.inputs?.target_username || igPinnedRun?.execution_context?.target_username;
    const isActive = ['running', 'queued', 'paused'].includes(status);
    const statusStyle = STATUS_STYLES[status] || STATUS_STYLES.pending;
    const runStartedAt =
        igPinnedRun?.started_at ||
        igPinnedRun?.task?.started_at ||
        igPinnedRun?.created_at ||
        forcedExecution?.startedAt ||
        null;
    const profileSessionPath =
        (igDebug?.sourceProfileRef ||
            igPinnedRun?.execution_context?.inputs?.user_data_dir ||
            null)?.toString().trim() || null;
    const profileSessionName = getProfileSessionName(profileSessionPath);
    const profileSourceHandle = (igDebug?.sourceAccountHandle || '').toString().trim() || null;

    const headerRight = supportsIGDebug ? (
        <button
            type="button"
            onClick={() => void fetchLatestIGDebug(true)}
            disabled={igDebugLoading}
            className="shrink-0 h-7 w-7 inline-flex items-center justify-center rounded bg-white text-gray-500 hover:bg-gray-50 hover:text-gray-700 dark:bg-gray-900/40 dark:text-gray-300 dark:hover:bg-gray-700 border border-gray-200 dark:border-gray-700 disabled:opacity-50 transition-colors"
            title="Refresh debug data"
            aria-label="Sync debug data"
        >
            <Loader2 className={`w-3.5 h-3.5 ${igDebugLoading ? 'animate-spin text-blue-500' : ''}`} />
        </button>
    ) : null;

    const statusSlot = (
        <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 min-w-0">
                <span className={`shrink-0 h-6 px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase border inline-flex items-center gap-1 ${statusStyle}`}>
                    {isActive && <Loader2 className="w-3 h-3 animate-spin opacity-70" />}
                    {status}
                </span>
                {isActive && (
                    <button
                        type="button"
                        onClick={() => igExecutionId && cancelExecution(igExecutionId)}
                        disabled={!igExecutionId || cancelBusyId === igExecutionId}
                        className="shrink-0 h-6 flex items-center gap-1 text-[10px] uppercase font-bold tracking-wide px-2 py-0.5 rounded bg-red-50 text-red-600 hover:bg-red-100 dark:bg-red-900/20 dark:text-red-400 dark:hover:bg-red-900/40 border border-transparent disabled:opacity-50 transition-colors"
                        title="Cancel this execution"
                    >
                        <X className="w-3 h-3" />
                        {cancelBusyId === igExecutionId ? 'Stopping' : 'Stop'}
                    </button>
                )}
            </div>
            <div className="flex items-center gap-1.5 shrink-0 text-[10px] text-gray-400">
                {runnerDebug.isConnected !== undefined && (
                    runnerDebug.isConnected
                        ? <Wifi className="w-3 h-3 text-green-500" />
                        : <WifiOff className="w-3 h-3 text-gray-400" />
                )}
                {runStartedAt && <span>{formatRelativeTime(runStartedAt)}</span>}
            </div>
        </div>
    );

    const igSpecificContent = supportsIGDebug ? (
        <div className="mt-3 space-y-3">
            {/* Error Message */}
            {igDebugError && (
                <div className="text-[10px] text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/10 border border-red-100 dark:border-red-900/30 px-2 py-1.5 rounded break-words">
                    {igDebugError}
                </div>
            )}

            {/* Waiting State */}
            {!igDebug && (
                <div className="text-[11px] text-gray-500 dark:text-gray-400 py-2">
                    {igExecutionId ? 'Waiting for run progress data…' : 'No execution data available.'}
                </div>
            )}

            {/* Progress Visualization */}
            {igDebug && (
                <div className="space-y-3">
                    {/* SCROLL PROGRESS */}
                    {typeof igDebug.savedDedupTargets === 'number' && typeof igDebug.expectedFollowing === 'number' && igDebug.expectedFollowing > 0 && (
                        <div>
                            <div className="flex items-end justify-between text-[10px] mb-1">
                                <span className="font-bold uppercase tracking-wider text-gray-600 dark:text-gray-400">Scroll (Extract List)</span>
                                <span className="font-medium text-gray-900 dark:text-gray-100">
                                    {Math.round((igDebug.savedDedupTargets / igDebug.expectedFollowing) * 100)}% 
                                    <span className="text-gray-500 ml-1 font-normal">({igDebug.savedDedupTargets}/{igDebug.expectedFollowing})</span>
                                </span>
                            </div>
                            <div className="h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                                <div
                                    className={`h-full rounded-full transition-all duration-500 ease-out ${igDebug.savedDedupTargets >= igDebug.expectedFollowing ? 'bg-green-500' : 'bg-blue-500'}`}
                                    style={{ width: `${Math.min(100, Math.round((igDebug.savedDedupTargets / igDebug.expectedFollowing) * 100))}%` }}
                                />
                            </div>
                        </div>
                    )}

                    {/* VISIT PROGRESS */}
                    {typeof igDebug.visitedCount === 'number' && typeof igDebug.savedDedupTargets === 'number' && igDebug.stage === 'visiting_pages' && igDebug.savedDedupTargets > 0 && (
                        <div>
                            <div className="flex items-end justify-between text-[10px] mb-1">
                                <span className="font-bold uppercase tracking-wider text-gray-600 dark:text-gray-400">Visit Accounts</span>
                                <span className="font-medium text-gray-900 dark:text-gray-100">
                                    {Math.round((igDebug.visitedCount / igDebug.savedDedupTargets) * 100)}% 
                                    <span className="text-gray-500 ml-1 font-normal">({igDebug.visitedCount}/{igDebug.savedDedupTargets})</span>
                                </span>
                            </div>
                            <div className="h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                                <div
                                    className={`h-full rounded-full transition-all duration-500 ease-out ${igDebug.visitedCount >= igDebug.savedDedupTargets ? 'bg-green-500' : 'bg-purple-500'}`}
                                    style={{ width: `${Math.min(100, Math.round((igDebug.visitedCount / igDebug.savedDedupTargets) * 100))}%` }}
                                />
                            </div>
                        </div>
                    )}

                    {/* STREAK RATIO */}
                    {isActive && igDebug.stage === 'scrolling' && typeof igDebug.streakRatio === 'number' && igDebug.streakRatio > 0 && (
                        <div>
                            <div className="flex items-end justify-between text-[10px] mb-1">
                                <span className="font-bold uppercase tracking-wider text-gray-600 dark:text-gray-400">Empty Scroll Streak</span>
                                <span className={`font-medium ${igDebug.streakRatio >= 0.7 ? 'text-red-500' : igDebug.streakRatio >= 0.4 ? 'text-amber-500' : 'text-green-500'}`}>
                                    {igDebug.noNewAccountsStreak} / 10
                                </span>
                            </div>
                            <div className="h-1 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                                <div
                                    className={`h-full rounded-full transition-all duration-500 ease-out ${igDebug.streakRatio >= 0.7 ? 'bg-red-500' : igDebug.streakRatio >= 0.4 ? 'bg-amber-500' : 'bg-green-500'}`}
                                    style={{ width: `${Math.min(100, Math.round(igDebug.streakRatio * 100))}%` }}
                                />
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Quick Stats Line */}
            {(seed || profileSessionName || igDebug) && (
                <div className="flex flex-col gap-2.5 border-t border-gray-100 dark:border-gray-700/50 pt-3">
                    <div className="flex flex-wrap gap-2">
                        {seed && (
                            <div className="text-[11px] font-mono text-gray-800 dark:text-gray-200 break-all bg-gray-50/80 dark:bg-gray-900/40 px-2 py-1.5 rounded-md border border-gray-100 dark:border-gray-700/50 inline-block w-fit">
                                <span className="text-gray-400 dark:text-gray-500 font-sans mr-1.5 font-medium tracking-wide text-[10px] uppercase">Target:</span>
                                @{seed}
                            </div>
                        )}
                        {profileSessionName && (
                            <div
                                title={profileSessionPath || undefined}
                                className="text-[11px] font-mono text-gray-800 dark:text-gray-200 break-all bg-gray-50/80 dark:bg-gray-900/40 px-2 py-1.5 rounded-md border border-gray-100 dark:border-gray-700/50 inline-block w-fit"
                            >
                                <span className="text-gray-400 dark:text-gray-500 font-sans mr-1.5 font-medium tracking-wide text-[10px] uppercase">Session:</span>
                                {profileSessionName}
                                {profileSourceHandle && (
                                    <span className="text-gray-400 dark:text-gray-500 font-sans ml-1.5">
                                        · @{profileSourceHandle}
                                    </span>
                                )}
                            </div>
                        )}
                    </div>
                    {igDebug && (
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] font-medium">
                            {igDebug.stage && (
                                <div>
                                    <span className="text-gray-400">Stage: </span>
                                    <span className="text-gray-800 dark:text-gray-200 capitalize">{igDebug.stage.replace('_', ' ')}</span>
                                    {typeof igDebug.iter === 'number' && <span className="text-gray-400 ml-1">· iter <span className="text-gray-800 dark:text-gray-200">{igDebug.iter}</span></span>}
                                </div>
                            )}
                            {(typeof igDebug.pageIndex === 'number' || typeof igDebug.pageTotal === 'number') && (
                                <div>
                                    <span className="text-gray-400">Pages: </span>
                                    <span className="text-gray-800 dark:text-gray-200">{igDebug.pageIndex ?? '?'} / {igDebug.pageTotal ?? '?'}</span>
                                </div>
                            )}
                            {igDebug.currentAccount && (
                                <div className="truncate max-w-[150px]">
                                    <span className="text-gray-400">At: </span>
                                    <button
                                        type="button"
                                        className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 hover:underline inline"
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            window.dispatchEvent(new CustomEvent('ig:scroll-to-account', { detail: { handle: igDebug.currentAccount, seed: seed || null } }));
                                        }}
                                    >
                                        @{igDebug.currentAccount}
                                    </button>
                                </div>
                            )}
                        </div>
                    )}
                    {igDebug && (
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] font-medium">
                            {typeof igDebug.targets === 'number' && (
                                <div><span className="text-gray-400">targets </span><span className="text-gray-800 dark:text-gray-200">{igDebug.targets}</span></div>
                            )}
                            {typeof igDebug.expectedFollowing === 'number' && (
                                <div><span className="text-gray-400">expected </span><span className="text-gray-800 dark:text-gray-200">{igDebug.expectedFollowing}</span></div>
                            )}
                            {typeof igDebug.savedDedupTargets === 'number' && (
                                <div><span className="text-gray-400">saved </span><span className="text-gray-800 dark:text-gray-200">{igDebug.savedDedupTargets}</span></div>
                            )}
                            {typeof igDebug.visitedCount === 'number' && (
                                <div><span className="text-gray-400">visited </span><span className="text-gray-800 dark:text-gray-200">{igDebug.visitedCount}</span></div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* Terminal Actions (Rerun) */}
            {igExecutionId && !isActive && igPinnedRun?.status && canRerunStatus(igPinnedRun.status) && (
                <div className="mt-4 bg-gray-50/80 dark:bg-gray-900/40 rounded-lg p-3.5 border border-gray-100 dark:border-gray-700/50">
                    <span className="block text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-2.5">
                        Rerun Actions
                    </span>
                    <div className="flex flex-col gap-3">
                        <div className="flex flex-wrap items-center gap-2">
                            <button
                                type="button"
                                onClick={() => rerunExecution(igExecutionId, { run_mode: 'full', visit_account_pages: true })}
                                disabled={rerunBusyId === igExecutionId}
                                className="px-3 py-1.5 text-xs rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-800 dark:text-gray-200 font-medium disabled:opacity-50 transition-colors shadow-sm"
                            >
                                Full Run
                            </button>
                            <button
                                type="button"
                                onClick={() => rerunExecution(igExecutionId, { run_mode: 'list', visit_account_pages: false })}
                                disabled={rerunBusyId === igExecutionId}
                                className="px-3 py-1.5 text-xs rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-800 dark:text-gray-200 font-medium disabled:opacity-50 transition-colors shadow-sm"
                            >
                                List Only
                            </button>
                            <button
                                type="button"
                                onClick={() => rerunExecution(igExecutionId, { run_mode: 'visit', visit_account_pages: true, allow_partial_resume: igRerunAllowPartial })}
                                disabled={rerunBusyId === igExecutionId}
                                className="px-3 py-1.5 text-xs rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-800 dark:text-gray-200 font-medium disabled:opacity-50 transition-colors shadow-sm"
                            >
                                Visit Only
                            </button>
                        </div>
                        <div className="flex items-center">
                            <label className="flex items-center gap-1.5 select-none cursor-pointer group w-fit">
                                <input
                                    type="checkbox"
                                    checked={igRerunAllowPartial}
                                    onChange={(e) => setIgRerunAllowPartial(e.target.checked)}
                                    className="w-3.5 h-3.5 rounded text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 transition-colors cursor-pointer"
                                />
                                <span className="text-[11px] font-medium text-gray-600 dark:text-gray-400 group-hover:text-gray-800 dark:group-hover:text-gray-200 transition-colors">
                                    Allow partial resume
                                </span>
                            </label>
                        </div>
                    </div>
                </div>
            )}

            {/* Banners (Zombie & Stuck) */}
            {igDebug && isActive && (
                <div className="mt-3 space-y-2">
                    {igDebug.isZombie && (
                        <div className="flex items-start gap-2 p-2 rounded text-[11px] leading-snug bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-800/50">
                            <Skull className="w-3.5 h-3.5 shrink-0 mt-0.5 text-purple-500" />
                            <div>
                                <span className="font-bold tracking-wide">ZOMBIE TASK</span>
                                <span className="block mt-0.5 opacity-90">Heartbeat is alive ({igDebug.heartbeatAgeSeconds != null ? `${igDebug.heartbeatAgeSeconds}s` : '?'}) but no progress for {igDebug.progressAgeSeconds != null ? `${Math.round(igDebug.progressAgeSeconds / 60)}m` : '?'}. Stop this safely and rerun.</span>
                            </div>
                        </div>
                    )}

                    {!igDebug.isZombie && (() => {
                        const mins = minutesAgo(igDebug.updatedAt);
                        const heartbeatOk = igDebug.heartbeatAgeSeconds !== null && igDebug.heartbeatAgeSeconds < 60;
                        const staleThreshold = heartbeatOk ? 30 : 5;
                        const warnThreshold = heartbeatOk ? 15 : 2;
                        
                        if (mins === null || mins < warnThreshold) return null;
                        const isStuck = !heartbeatOk || mins >= staleThreshold;
                        
                        return (
                            <div className={`flex items-start justify-between gap-3 p-2 rounded text-[11px] leading-snug ${isStuck ? 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800/50' : 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800/50'}`}>
                                <div className="flex gap-2">
                                    <AlertCircle className={`w-3.5 h-3.5 shrink-0 mt-0.5 ${isStuck ? 'text-red-500' : 'text-amber-500'}`} />
                                    <div>
                                        <span className="font-bold tracking-wide">{isStuck ? 'TASK STUCK' : 'TASK STALLED'}</span>
                                        <span className="block mt-0.5 opacity-90">No progression for {mins}m. Memory limits or rate limits may have been hit.</span>
                                    </div>
                                </div>
                                {isStuck && (
                                    <button
                                        type="button"
                                        className="shrink-0 whitespace-nowrap px-2 py-1 rounded text-[10px] font-bold uppercase tracking-wider bg-white dark:bg-gray-800 border border-red-200 dark:border-red-800 hover:bg-red-50 dark:hover:bg-red-900/40 transition-colors"
                                        onClick={async (e) => {
                                            e.stopPropagation();
                                            const btn = e.currentTarget;
                                            btn.disabled = true;
                                            btn.textContent = 'Restarting...';
                                            try {
                                                const resp = await fetch('/api/v1/system-settings/restart', { method: 'POST', body: JSON.stringify({ service: 'runner' }) });
                                                const data = await resp.json().catch(() => ({}));
                                                btn.textContent = data.success ? 'Restart Sent' : 'Failed';
                                            } catch {
                                                btn.textContent = 'Error';
                                            }
                                            setTimeout(() => { btn.textContent = 'Restart Runner'; btn.disabled = false; }, 3000);
                                        }}
                                    >
                                        Restart Runner
                                    </button>
                                )}
                            </div>
                        );
                    })()}
                </div>
            )}

            {/* Details Accordion (Esoteric Debug Info) */}
            {igDebug && (
                <div className="mt-3">
                    <button
                        onClick={() => setIgDebugExpanded(!igDebugExpanded)}
                        className="w-full flex items-center justify-between p-1.5 text-[10px] font-bold uppercase tracking-widest text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors group"
                    >
                        <span>Details & Raw Output</span>
                        {igDebugExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </button>
                    
                    {igDebugExpanded && (
                        <div className="mt-2 text-[10px] bg-gray-50 dark:bg-gray-900/40 rounded p-2.5 border border-gray-100 dark:border-gray-800 font-mono text-gray-700 dark:text-gray-300 space-y-2">
                            <div className="flex items-center gap-2">
                                <span className="opacity-50">exec_id</span>
                                <span className="truncate">{igExecutionId}</span>
                                <button type="button" onClick={() => void copyExecutionId()} className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded ml-auto flex-shrink-0"><Copy className="w-3 h-3" /></button>
                            </div>
                            
                            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 opacity-90">
                                {igDebug.runnerId && <div><span className="opacity-50 inline-block w-16">runner</span> {igDebug.runnerId.split('-')[0]}</div>}
                                {igDebug.executionBackendHint && <div><span className="opacity-50 inline-block w-16">backend</span> {igDebug.executionBackendHint}</div>}
                                <div><span className="opacity-50 inline-block w-16">scroll</span> {igDebug.scrollMode || 'N/A'}</div>
                                <div><span className="opacity-50 inline-block w-16">run_mode</span> {igDebug.runMode || 'N/A'}</div>
                                {igDebug.heartbeatAgeSeconds !== null && <div><span className="opacity-50 inline-block w-16">heartbeat</span> {igDebug.heartbeatAgeSeconds}s ago</div>}
                                <div><span className="opacity-50 inline-block w-16">bottom</span> {igDebug.reachedBottom ? 'true' : 'false'}</div>
                                {typeof igDebug.noNewAccountsStreak === 'number' && <div><span className="opacity-50 inline-block w-16">no_new</span> {igDebug.noNewAccountsStreak}</div>}
                                {typeof igDebug.noChangeCount === 'number' && <div><span className="opacity-50 inline-block w-16">no_change</span> {igDebug.noChangeCount}</div>}
                                {igDebug.visitAccountPages !== null && <div><span className="opacity-50 inline-block w-16">visit_pages</span> {igDebug.visitAccountPages ? 'yes' : 'no'}</div>}
                                {igDebug.allowPartialResume !== null && <div><span className="opacity-50 inline-block w-16">partial_ok</span> {igDebug.allowPartialResume ? 'yes' : 'no'}</div>}
                                {igDebug.stopReason && <div className="col-span-2"><span className="opacity-50 inline-block w-16">stop</span> {igDebug.stopReason}</div>}
                                {igDebug.errorType && <div className="col-span-2"><span className="opacity-50 inline-block w-16">error</span> <span className="text-red-500">{igDebug.errorType}</span></div>}
                            </div>

                            {/* Screenshots List */}
                            {igDebug.screenshots.length > 0 && (
                                <div className="mt-3 pt-2 border-t border-gray-200 dark:border-gray-700">
                                    <div className="opacity-50 mb-1">screenshots</div>
                                    <div className="flex flex-col gap-1">
                                        {igDebug.screenshots.slice(-4).map((p, idx) => (
                                            <a
                                                key={`${p}-${idx}`}
                                                href={screenshotUrl(igDebug.executionId!, p)}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="text-blue-600 dark:text-blue-400 hover:underline truncate"
                                            >
                                                {p.split('/').pop()}
                                            </a>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Fallback screenshot if error occurs before real screenshots */}
                            {igDebug.screenshots.length === 0 && (igDebug.stage === 'error' || !!igDebug.errorMessage) && (
                                <div className="mt-3 pt-2 border-t border-gray-200 dark:border-gray-700">
                                    <div className="opacity-50 mb-1">fallback screenshot</div>
                                    <a
                                        href={screenshotUrl(igDebug.executionId!, 'ig_debug_profile.png')}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="text-blue-600 dark:text-blue-400 hover:underline"
                                    >
                                        ig_debug_profile.png
                                    </a>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}
        </div>
    ) : (
        <div className="mt-3 space-y-3">
            {runDetailItems.length > 0 && (
                <div className="flex flex-col gap-1.5 text-[10px] font-medium text-gray-700 dark:text-gray-300">
                    {runDetailItems.map((item) => (
                        <div key={`${item.label}-${item.value}`} className="flex items-start gap-2">
                            <span className="w-16 shrink-0 text-gray-400 uppercase tracking-wide">{item.label}</span>
                            <span className="break-all">{item.value}</span>
                        </div>
                    ))}
                </div>
            )}

            {runDetailItems.length === 0 && (
                <div className="text-[11px] text-gray-500 dark:text-gray-400">
                    No task detail fields available.
                </div>
            )}
        </div>
    );

    return (
        <div className="mb-4">
            <RunnerTaskCard
                status={status}
                playbookCode={igPinnedRun?.playbook_code}
                title={formatTaskTitle(playbookCode)}
                queuePosition={runnerDebug.queuePosition}
                queueTotal={runnerDebug.queueTotal}
                dependencyHold={runnerDebug.dependencyHold}
                heartbeatAt={runnerDebug.heartbeatAt || igDebug?.heartbeatAt}
                runnerId={runnerDebug.runnerId || igDebug?.runnerId}
                isConnected={runnerDebug.isConnected}
                progress={runnerDebug.progress}
                executionId={igExecutionId || undefined}
                error={igDebugError || igPinnedRun?.task?.error || igPinnedRun?.failure_reason || null}
                createdAt={igPinnedRun?.created_at}
                headerRight={headerRight}
                statusSlot={statusSlot}
                extensionSlot={igSpecificContent}
            />
        </div>
    );
}
