import React from 'react';
import {
    CheckCircle2,
    ChevronDown,
    ChevronUp,
    Circle,
    ExternalLink,
    Loader2,
    MoreHorizontal,
    Play,
    Square,
    Trash2,
} from 'lucide-react';

import type { SeedInfo } from '../insightsApi';
import type { SeedExecution, RunInfo } from '../hooks/useSeedExecutions';
import type { IGDebugInfo } from './SeedExecutionBar';
import { SeedExecutionBar } from './SeedExecutionBar';
import { SeedDebugPanel } from './SeedDebugPanel';
import { getAvatarUrl, getProxiedImageUrl } from '../utils';

interface SeedCardProps {
    workspaceId: string;
    seed: SeedInfo;
    onViewInsights: (seed: string) => void;
    onReCrawl: (seed: string) => void;
    onRemove?: (seed: string) => void;
    /** Execution state for this seed (from useSeedExecutions) */
    seedExecution?: SeedExecution | null;
    /** Debug info for inline progress (from parent SSE) */
    igDebug?: IGDebugInfo | null;
    /** API URL for debug panel screenshot links */
    apiUrl?: string;
    /** Rerun handler */
    onRerun?: (executionId: string, overrideInputs?: Record<string, any>) => Promise<void>;
    /** Cancel handler */
    onCancel?: (executionId: string) => Promise<void>;
    /** Whether a rerun is in progress */
    rerunBusyId?: string | null;
    /** Whether a cancel is in progress */
    cancelBusyId?: string | null;
}

const StatusDot = ({ active, label }: { active: boolean; label: string }) => (
    <span className="inline-flex items-center gap-1 text-xs">
        {active ? (
            <CheckCircle2 className="w-3 h-3 text-green-500" />
        ) : (
            <Circle className="w-3 h-3 text-gray-400" />
        )}
        <span className={active ? 'text-green-600 dark:text-green-400' : 'text-gray-400 dark:text-gray-500'}>
            {label}
        </span>
    </span>
);

export function SeedCard({
    workspaceId,
    seed,
    onViewInsights,
    onReCrawl,
    onRemove,
    seedExecution,
    igDebug,
    apiUrl,
    onRerun,
    onCancel,
    rerunBusyId,
    cancelBusyId,
}: SeedCardProps) {
    const [menuOpen, setMenuOpen] = React.useState(false);
    const [debugOpen, setDebugOpen] = React.useState(false);

    const formattedDate = seed.last_crawled
        ? new Date(seed.last_crawled).toLocaleString()
        : 'Never';

    const exec = seedExecution || null;
    const status = exec?.status || 'idle';
    const latestRun = exec?.latestRun || null;
    const executionId = (latestRun?.execution_id || latestRun?.id || '').toString();
    const isActive = status === 'running' || status === 'pending';
    const isTerminal = status === 'completed' || status === 'failed';
    const errorMessage = latestRun?.task?.error || latestRun?.failure_reason || null;
    const blockedReason =
        (typeof latestRun?.execution_context?.blocked_reason === 'string'
            ? latestRun.execution_context.blocked_reason
            : null) ||
        null;

    // Border color based on status
    const borderClass = status === 'running'
        ? 'border-blue-400 dark:border-blue-500'
        : status === 'pending'
            ? 'border-amber-400 dark:border-amber-500'
            : status === 'failed'
                ? 'border-red-300 dark:border-red-600'
                : 'border-gray-200 dark:border-gray-700 hover:border-blue-400 dark:hover:border-blue-500';

    return (
        <div
            className={`bg-white dark:bg-gray-800 rounded-lg border ${borderClass} p-4 transition-colors cursor-pointer`}
            onClick={() => onViewInsights(seed.seed)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === 'Enter') onViewInsights(seed.seed); }}
        >
            {/* Header */}
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                    <img
                        src={getProxiedImageUrl('', seed.profile_picture_url || undefined) || getAvatarUrl(seed.seed)}
                        alt={seed.seed}
                        className="w-8 h-8 rounded-full object-cover bg-gray-200 dark:bg-gray-700"
                        onError={(e) => {
                            const img = e.target as HTMLImageElement;
                            const fallback = getAvatarUrl(seed.seed);
                            if (img.src !== fallback) img.src = fallback;
                        }}
                    />
                    <div>
                        <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                            @{seed.seed}
                        </div>
                        <div className="text-xs text-gray-500 dark:text-gray-400">
                            {seed.target_count}{seed.expected_count ? `/${seed.expected_count}` : ''} targets
                            {seed.target_count > 0 && (
                                <span className={seed.visited_count >= seed.target_count
                                    ? 'text-green-600 dark:text-green-400'
                                    : seed.visited_count > 0
                                        ? 'text-blue-600 dark:text-blue-400'
                                        : ''
                                }>
                                    {' · '}{seed.visited_count}/{seed.target_count} visited
                                </span>
                            )}
                            {' · '}Last: {formattedDate}
                        </div>
                    </div>
                </div>

                {/* Menu */}
                {/* eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions */}
                <div className="relative" onClick={(e) => e.stopPropagation()}>
                    <button
                        onClick={() => setMenuOpen(!menuOpen)}
                        className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
                    >
                        <MoreHorizontal className="w-4 h-4 text-gray-500" />
                    </button>
                    {menuOpen && (
                        <div className="absolute right-0 top-8 z-10 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg py-1 w-40">
                            <button
                                onClick={() => {
                                    window.open(`https://instagram.com/${seed.seed}`, '_blank');
                                    setMenuOpen(false);
                                }}
                                className="flex items-center gap-2 w-full px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                            >
                                <ExternalLink className="w-3 h-3" />
                                Open in IG
                            </button>
                            {onRemove && (
                                <button
                                    onClick={() => {
                                        onRemove(seed.seed);
                                        setMenuOpen(false);
                                    }}
                                    className="flex items-center gap-2 w-full px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
                                >
                                    <Trash2 className="w-3 h-3" />
                                    Remove Seed
                                </button>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* Execution Status Bar */}
            {status !== 'idle' && (
                <SeedExecutionBar
                    status={status}
                    queuePosition={exec?.queuePosition}
                    debug={isActive ? (igDebug || null) : null}
                    blockedReason={blockedReason}
                    errorMessage={errorMessage as string | null}
                />
            )}

            {/* Analysis Status Dots */}
            <div className="flex flex-wrap gap-3 mb-3 mt-3">
                <StatusDot active={seed.has_tags} label="Tags" />
                <StatusDot active={seed.has_posts} label="Content" />
                <StatusDot active={seed.has_network} label="Network" />
                <StatusDot active={seed.has_personas} label="Persona" />
            </div>

            {/* Action Buttons — stopPropagation to avoid triggering card click */}
            {/* eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions */}
            <div className="flex items-center gap-2 flex-wrap" onClick={(e) => e.stopPropagation()}>
                {/* Cancel button for active executions */}
                {isActive && executionId && onCancel && (
                    <button
                        onClick={() => onCancel(executionId)}
                        disabled={cancelBusyId === executionId}
                        className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 rounded-md hover:bg-red-100 dark:hover:bg-red-900/40 transition-colors disabled:opacity-50"
                    >
                        <Square className="w-3 h-3" />
                        {cancelBusyId === executionId ? 'Cancelling…' : 'Cancel'}
                    </button>
                )}

                {/* Rerun buttons for terminal executions */}
                {isTerminal && executionId && onRerun && (
                    <>
                        <button
                            onClick={() => onRerun(executionId, { target_username: seed.seed, run_mode: 'full', visit_account_pages: true })}
                            disabled={rerunBusyId === executionId}
                            className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors disabled:opacity-50"
                            title="Full analysis (scroll + visit)"
                        >
                            <Play className="w-3 h-3" />
                            {rerunBusyId === executionId ? 'Running…' : 'Full'}
                        </button>
                        <button
                            onClick={() => onRerun(executionId, { target_username: seed.seed, run_mode: 'list', visit_account_pages: false })}
                            disabled={rerunBusyId === executionId}
                            className="px-2.5 py-1.5 text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors disabled:opacity-50"
                            title="Only extract the following list"
                        >
                            {rerunBusyId === executionId ? 'Running…' : 'List Only'}
                        </button>
                        <button
                            onClick={() => onRerun(executionId, { target_username: seed.seed, run_mode: 'visit', visit_account_pages: true })}
                            disabled={rerunBusyId === executionId}
                            className="px-2.5 py-1.5 text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors disabled:opacity-50"
                            title="Only visit pages using existing list"
                        >
                            {rerunBusyId === executionId ? 'Running…' : 'Visit Pages'}
                        </button>
                    </>
                )}

                {/* Default Crawl/Re-crawl when idle */}
                {status === 'idle' && (
                    <button
                        onClick={() => onReCrawl(seed.seed)}
                        className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                    >
                        <Play className="w-3 h-3" />
                        {seed.target_count > 0 ? 'Re-crawl' : 'Crawl'}
                    </button>
                )}



                {/* Debug toggle (show when execution exists) */}
                {executionId && (
                    <button
                        onClick={() => setDebugOpen(!debugOpen)}
                        className="ml-auto flex items-center gap-0.5 px-2 py-1.5 text-[10px] font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
                        title={debugOpen ? 'Hide debug' : 'Show debug'}
                    >
                        {debugOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                        debug
                    </button>
                )}
            </div>

            {/* Expandable Debug Panel */}
            {debugOpen && executionId && apiUrl && (
                <SeedDebugPanel
                    workspaceId={workspaceId}
                    executionId={executionId}
                    apiUrl={apiUrl}
                    debug={igDebug || null}
                    status={status}
                    errorMessage={errorMessage as string | null}
                />
            )}
        </div>
    );
}
