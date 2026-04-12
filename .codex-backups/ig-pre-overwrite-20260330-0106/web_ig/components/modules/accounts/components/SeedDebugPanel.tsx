import React from 'react';
import { Copy, ExternalLink } from 'lucide-react';
import type { IGDebugInfo } from './SeedExecutionBar';
import { useIGDebug } from '../../../workbench/components/WorkbenchExecutionPanel/hooks/useIGDebug';

export interface SeedDebugPanelProps {
    workspaceId: string;
    executionId: string;
    apiUrl: string;
    debug: IGDebugInfo | null;
    status?: string | null;
    errorMessage?: string | null;
}

function buildFallbackDebug(
    executionId: string,
    debug: IGDebugInfo | null,
    status?: string | null,
    errorMessage?: string | null,
): IGDebugInfo | null {
    const normalizedDebug = debug && debug.executionId === executionId ? debug : null;

    if (normalizedDebug) {
        return {
            ...normalizedDebug,
            stage: normalizedDebug.stage || ((status || '').toString().trim().toLowerCase() === 'failed' ? 'error' : normalizedDebug.stage),
            errorMessage: normalizedDebug.errorMessage || errorMessage || null,
        };
    }

    if (!errorMessage && !status) return null;

    const normalizedStatus = (status || '').toString().trim().toLowerCase();
    return {
        executionId,
        updatedAt: null,
        stage: normalizedStatus === 'failed' ? 'error' : (normalizedStatus || null),
        iter: null,
        targets: null,
        expectedFollowing: null,
        stopReason: null,
        savedDedupTargets: null,
        visitedCount: null,
        pageIndex: null,
        pageTotal: null,
        currentAccount: null,
        noChangeCount: null,
        noNewAccountsStreak: null,
        reachedBottom: null,
        errorType: null,
        errorMessage: errorMessage || null,
        scrollMode: null,
        runMode: null,
        executionBackendHint: null,
        visitAccountPages: null,
        listCaptureStatus: null,
        allowPartialResume: null,
        screenshots: [],
    };
}

export function SeedDebugPanel({
    workspaceId,
    executionId,
    apiUrl,
    debug,
    status,
    errorMessage,
}: SeedDebugPanelProps) {
    const {
        igDebug: fetchedDebug,
        igDebugLoading,
        fetchLatestIGDebug,
    } = useIGDebug({
        apiUrl,
        workspaceId,
        executionId,
    });

    React.useEffect(() => {
        if (!executionId || !workspaceId) return;
        void fetchLatestIGDebug(true);
    }, [executionId, workspaceId, fetchLatestIGDebug]);

    const panelDebug = React.useMemo(
        () => buildFallbackDebug(executionId, (fetchedDebug as IGDebugInfo | null) || debug, status, errorMessage),
        [debug, errorMessage, executionId, fetchedDebug, status],
    );

    if (igDebugLoading && !panelDebug) {
        return (
            <div className="mt-3 border-t border-gray-200 dark:border-gray-600 pt-3 text-xs text-gray-400">
                Loading debug…
            </div>
        );
    }

    if (!panelDebug) {
        return (
            <div className="mt-3 border-t border-gray-200 dark:border-gray-600 pt-3 text-xs text-gray-400">
                No debug data available.
            </div>
        );
    }

    const screenshotUrl = (fullPath: string) => {
        const basename = fullPath.split('/').pop() || fullPath;
        return `${apiUrl}/api/v1/playbooks/execute/${executionId}/debug-screenshot?file=${encodeURIComponent(basename)}&_t=${Date.now()}`;
    };

    return (
        <div className="mt-3 border-t border-gray-200 dark:border-gray-600 pt-3 space-y-2 text-xs">
            {/* Execution ID */}
            <div className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400">
                <span className="font-medium text-gray-600 dark:text-gray-300">exec</span>
                <span className="font-mono text-[10px] truncate max-w-[180px]">{executionId}</span>
                <button
                    onClick={() => navigator.clipboard.writeText(executionId)}
                    className="p-0.5 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                    title="Copy execution ID"
                >
                    <Copy className="w-3 h-3" />
                </button>
            </div>

            {/* Stage & metadata grid */}
            <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[10px]">
                {panelDebug.stage && <MetaItem label="stage" value={panelDebug.stage} />}
                {panelDebug.iter != null && <MetaItem label="iter" value={String(panelDebug.iter)} />}
                {panelDebug.targets != null && <MetaItem label="targets" value={String(panelDebug.targets)} />}
                {panelDebug.expectedFollowing != null && <MetaItem label="expected" value={String(panelDebug.expectedFollowing)} />}
                {panelDebug.savedDedupTargets != null && <MetaItem label="saved" value={String(panelDebug.savedDedupTargets)} />}
                {panelDebug.visitedCount != null && <MetaItem label="visited" value={String(panelDebug.visitedCount)} />}
                {panelDebug.pageIndex != null && panelDebug.pageTotal != null && (
                    <MetaItem label="pages" value={`${panelDebug.pageIndex}/${panelDebug.pageTotal}`} />
                )}
                {panelDebug.stopReason && <MetaItem label="stop" value={panelDebug.stopReason} />}
                {panelDebug.scrollMode && <MetaItem label="scroll_mode" value={panelDebug.scrollMode} />}
                {panelDebug.noNewAccountsStreak != null && <MetaItem label="no_new_streak" value={String(panelDebug.noNewAccountsStreak)} />}
                {panelDebug.noChangeCount != null && <MetaItem label="no_change" value={String(panelDebug.noChangeCount)} />}
                {panelDebug.reachedBottom != null && <MetaItem label="bottom" value={panelDebug.reachedBottom ? 'yes' : 'no'} />}
                {panelDebug.executionBackendHint && <MetaItem label="backend" value={panelDebug.executionBackendHint} />}
                {panelDebug.visitAccountPages != null && <MetaItem label="visit_pages" value={panelDebug.visitAccountPages ? 'yes' : 'no'} />}
            </div>

            {/* Last updated */}
            {panelDebug.updatedAt && (
                <div className="text-[10px] text-gray-400">
                    last update {new Date(panelDebug.updatedAt).toLocaleString()}
                </div>
            )}

            {/* Error details */}
            {panelDebug.errorMessage && (
                <div className="bg-red-50 dark:bg-red-900/20 rounded p-2 text-[10px] text-red-700 dark:text-red-300 break-words">
                    {panelDebug.errorType && <span className="font-medium">{panelDebug.errorType}: </span>}
                    {panelDebug.errorMessage}
                </div>
            )}

            {/* Screenshots */}
            {panelDebug.screenshots.length > 0 && (
                <div>
                    <div className="text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-1">Screenshots</div>
                    <div className="space-y-1">
                        {panelDebug.screenshots.map((path, i) => {
                            const basename = path.split('/').pop() || path;
                            return (
                                <a
                                    key={i}
                                    href={screenshotUrl(path)}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="flex items-center gap-1 text-[10px] text-blue-600 dark:text-blue-400 hover:underline bg-gray-50 dark:bg-gray-700/50 rounded px-2 py-1"
                                >
                                    <ExternalLink className="w-3 h-3 flex-shrink-0" />
                                    <span className="truncate">{basename.length > 35 ? basename.slice(0, 35) + '…' : basename}</span>
                                </a>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
}

function MetaItem({ label, value }: { label: string; value: string }) {
    return (
        <div className="flex items-center gap-1 text-gray-500 dark:text-gray-400">
            <span className="font-medium text-gray-600 dark:text-gray-300">{label}</span>
            <span className="truncate">{value}</span>
        </div>
    );
}
