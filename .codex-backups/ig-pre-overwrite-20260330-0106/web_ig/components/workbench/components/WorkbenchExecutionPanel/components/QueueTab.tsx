import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronRight, Loader2, RefreshCw } from 'lucide-react';

import type { QueueGroupSummary, RunInfo } from '../types';
import { formatRelativeTime } from '../utils/formatters';
import { getRunPrimarySubject } from '../utils';
import { RunLogCard } from './RunLogCard';

interface QueueChildrenState {
    executions: RunInfo[];
    total: number;
    hasMore: boolean;
    loading: boolean;
    error: string | null;
}

interface QueueTabProps {
    workspaceId: string;
    apiUrl: string;
    rerunBusyId: string | null;
    igRerunAllowPartial: boolean;
    canRerunStatus: (status: any) => boolean;
    rerunExecution: (executionId: string, overrideInputs?: Record<string, any>) => Promise<void>;
}

function GroupSummaryBadge(props: { label: string; value: number; tone: string }) {
    const { label, value, tone } = props;
    return (
        <span className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[10px] font-medium ${tone}`}>
            <span>{label}</span>
            <span className="tabular-nums">{value}</span>
        </span>
    );
}

export function QueueTab({
    workspaceId,
    apiUrl,
    rerunBusyId,
    igRerunAllowPartial,
    canRerunStatus,
    rerunExecution,
}: QueueTabProps) {
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [groups, setGroups] = useState<QueueGroupSummary[]>([]);
    const [ungroupedRuns, setUngroupedRuns] = useState<RunInfo[]>([]);
    const [groupsOffset, setGroupsOffset] = useState(0);
    const [hasMoreGroups, setHasMoreGroups] = useState(false);
    const [loadingMoreGroups, setLoadingMoreGroups] = useState(false);
    const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
    const [childrenByGroup, setChildrenByGroup] = useState<Record<string, QueueChildrenState>>({});

    const summaryAbortRef = useRef<AbortController | null>(null);
    const childAbortRef = useRef<Record<string, AbortController>>({});

    const cardProps = useMemo(
        () => ({ workspaceId, rerunBusyId, igRerunAllowPartial, canRerunStatus, rerunExecution }),
        [workspaceId, rerunBusyId, igRerunAllowPartial, canRerunStatus, rerunExecution],
    );

    const fetchQueueSummary = useCallback(async (reset = true) => {
        const nextOffset = reset ? 0 : groupsOffset;
        if (reset) {
            setLoading(true);
            setError(null);
            summaryAbortRef.current?.abort();
        } else {
            setLoadingMoreGroups(true);
        }

        const controller = new AbortController();
        summaryAbortRef.current = controller;
        try {
            const response = await fetch(
                `${apiUrl}/api/v1/ig/workbench/queue-groups?workspace_id=${workspaceId}&limit=12&offset=${nextOffset}`,
                {
                    signal: controller.signal,
                    headers: { 'Content-Type': 'application/json' },
                },
            );
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            const nextGroups = Array.isArray(data.groups) ? data.groups : [];
            const nextUngrouped = Array.isArray(data.ungrouped) ? data.ungrouped : [];

            setGroups((prev) => (reset ? nextGroups : [...prev, ...nextGroups]));
            if (reset) {
                setUngroupedRuns(nextUngrouped);
            }
            setGroupsOffset(nextOffset + nextGroups.length);
            setHasMoreGroups(Boolean(data.has_more_groups));
        } catch (err) {
            if ((err as Error)?.name === 'AbortError') return;
            const message = err instanceof Error ? err.message : 'Failed to load queue groups';
            setError(message);
        } finally {
            if (reset) {
                setLoading(false);
            } else {
                setLoadingMoreGroups(false);
            }
        }
    }, [apiUrl, groupsOffset, workspaceId]);

    const fetchGroupChildren = useCallback(async (parentExecutionId: string, reset = true) => {
        childAbortRef.current[parentExecutionId]?.abort();
        const current = childrenByGroup[parentExecutionId];
        const offset = reset ? 0 : (current?.executions.length || 0);
        const controller = new AbortController();
        childAbortRef.current[parentExecutionId] = controller;

        setChildrenByGroup((prev) => ({
            ...prev,
            [parentExecutionId]: {
                executions: reset ? [] : (prev[parentExecutionId]?.executions || []),
                total: prev[parentExecutionId]?.total || 0,
                hasMore: prev[parentExecutionId]?.hasMore || false,
                loading: true,
                error: null,
            },
        }));

        try {
            const response = await fetch(
                `${apiUrl}/api/v1/ig/workbench/queue-groups/${parentExecutionId}/children?workspace_id=${workspaceId}&limit=20&offset=${offset}`,
                {
                    signal: controller.signal,
                    headers: { 'Content-Type': 'application/json' },
                },
            );
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            const nextExecutions = Array.isArray(data.executions) ? data.executions : [];
            setChildrenByGroup((prev) => ({
                ...prev,
                [parentExecutionId]: {
                    executions: reset
                        ? nextExecutions
                        : [...(prev[parentExecutionId]?.executions || []), ...nextExecutions],
                    total: Number(data.total || 0),
                    hasMore: Boolean(data.has_more),
                    loading: false,
                    error: null,
                },
            }));
        } catch (err) {
            if ((err as Error)?.name === 'AbortError') return;
            const message = err instanceof Error ? err.message : 'Failed to load group executions';
            setChildrenByGroup((prev) => ({
                ...prev,
                [parentExecutionId]: {
                    executions: prev[parentExecutionId]?.executions || [],
                    total: prev[parentExecutionId]?.total || 0,
                    hasMore: prev[parentExecutionId]?.hasMore || false,
                    loading: false,
                    error: message,
                },
            }));
        }
    }, [apiUrl, childrenByGroup, workspaceId]);

    const toggleGroup = useCallback((parentExecutionId: string) => {
        setExpandedGroups((prev) => {
            const next = new Set(prev);
            if (next.has(parentExecutionId)) {
                next.delete(parentExecutionId);
                childAbortRef.current[parentExecutionId]?.abort();
                delete childAbortRef.current[parentExecutionId];
                setChildrenByGroup((current) => {
                    const copy = { ...current };
                    delete copy[parentExecutionId];
                    return copy;
                });
                return next;
            }
            next.add(parentExecutionId);
            return next;
        });
        if (!expandedGroups.has(parentExecutionId)) {
            void fetchGroupChildren(parentExecutionId, true);
        }
    }, [expandedGroups, fetchGroupChildren]);

    useEffect(() => {
        void fetchQueueSummary(true);
        return () => {
            summaryAbortRef.current?.abort();
            Object.values(childAbortRef.current).forEach((controller) => controller.abort());
        };
    }, [fetchQueueSummary]);

    return (
        <div className="space-y-3">
            <div className="flex items-center justify-between">
                <div>
                    <div className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                        Queue Explorer
                    </div>
                    <div className="text-[11px] text-gray-500 dark:text-gray-400">
                        Group summary first. Expand to load only that batch.
                    </div>
                </div>
                <button
                    type="button"
                    onClick={() => void fetchQueueSummary(true)}
                    disabled={loading}
                    className="inline-flex h-7 w-7 items-center justify-center rounded border border-gray-200 bg-white text-gray-500 hover:bg-gray-50 hover:text-gray-700 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
                    title="Refresh queue summary"
                >
                    <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
                </button>
            </div>

            {loading && groups.length === 0 && ungroupedRuns.length === 0 ? (
                <div className="flex items-center justify-center rounded-lg border border-dashed border-gray-200 px-3 py-8 text-xs text-gray-500 dark:border-gray-700 dark:text-gray-400">
                    <Loader2 className="mr-2 h-4 w-4 animate-spin text-blue-500" />
                    Loading queue groups...
                </div>
            ) : error ? (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-3 text-xs text-red-700 dark:border-red-900/50 dark:bg-red-900/10 dark:text-red-300">
                    Failed to load queue summary: {error}
                </div>
            ) : (
                <>
                    {ungroupedRuns.length > 0 && (
                        <div className="rounded-lg border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
                            <div className="border-b border-gray-100 px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500 dark:border-gray-700 dark:text-gray-400">
                                Single Runs
                            </div>
                            {ungroupedRuns.map((run, index) => (
                                <RunLogCard
                                    key={run.id || run.execution_id || `ungrouped-${index}`}
                                    run={run}
                                    index={index}
                                    {...cardProps}
                                />
                            ))}
                        </div>
                    )}

                    {groups.length === 0 ? (
                        <div className="rounded-lg border border-dashed border-gray-200 px-3 py-6 text-xs text-gray-500 dark:border-gray-700 dark:text-gray-400">
                            No grouped backlog/history yet.
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {groups.map((group) => {
                                const isExpanded = expandedGroups.has(group.parent_execution_id);
                                const children = childrenByGroup[group.parent_execution_id];
                                const representative = group.representative_run;
                                const subject = getRunPrimarySubject(representative);

                                return (
                                    <div
                                        key={group.parent_execution_id}
                                        className="overflow-hidden rounded-lg border border-indigo-200 bg-indigo-50/30 dark:border-indigo-800/50 dark:bg-indigo-900/10"
                                    >
                                        <button
                                            type="button"
                                            onClick={() => toggleGroup(group.parent_execution_id)}
                                            className="flex w-full items-start gap-2 px-3 py-3 text-left transition-colors hover:bg-indigo-100/50 dark:hover:bg-indigo-900/20"
                                        >
                                            <ChevronRight
                                                className={`mt-0.5 h-4 w-4 shrink-0 text-indigo-500 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                                            />
                                            <div className="min-w-0 flex-1">
                                                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                                                    <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-400">
                                                        Batch Group
                                                    </span>
                                                    <span className="text-xs font-semibold text-gray-900 dark:text-gray-100">
                                                        {(representative.playbook_code || '').replace(/^ig_/, '').replace(/_/g, ' ')}
                                                    </span>
                                                    {subject && (
                                                        <span className="truncate font-mono text-[10px] text-gray-500 dark:text-gray-400">
                                                            {subject.value}
                                                        </span>
                                                    )}
                                                </div>
                                                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                                                    <GroupSummaryBadge label="Total" value={group.summary.total} tone="border-gray-200 text-gray-600 dark:border-gray-700 dark:text-gray-300" />
                                                    <GroupSummaryBadge label="Running" value={group.summary.running} tone="border-sky-200 text-sky-700 dark:border-sky-800/50 dark:text-sky-300" />
                                                    <GroupSummaryBadge label="Pending" value={group.summary.pending} tone="border-amber-200 text-amber-700 dark:border-amber-800/50 dark:text-amber-300" />
                                                    <GroupSummaryBadge label="Done" value={group.summary.completed} tone="border-green-200 text-green-700 dark:border-green-800/50 dark:text-green-300" />
                                                    <GroupSummaryBadge label="Failed" value={group.summary.failed} tone="border-red-200 text-red-700 dark:border-red-800/50 dark:text-red-300" />
                                                </div>
                                            </div>
                                            <div className="shrink-0 text-right">
                                                <div className="text-[10px] text-gray-400 dark:text-gray-500">
                                                    {group.latest_at ? formatRelativeTime(group.latest_at) : ''}
                                                </div>
                                                <div
                                                    className="mt-1 cursor-pointer font-mono text-[9px] text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
                                                    onClick={(event) => {
                                                        event.stopPropagation();
                                                        navigator.clipboard.writeText(group.parent_execution_id);
                                                    }}
                                                    title={`Parent: ${group.parent_execution_id}`}
                                                >
                                                    {group.parent_execution_id.slice(0, 8)}…
                                                </div>
                                            </div>
                                        </button>

                                        {isExpanded && (
                                            <div className="border-t border-indigo-200 dark:border-indigo-800/50">
                                                {children?.loading && children.executions.length === 0 ? (
                                                    <div className="flex items-center px-3 py-4 text-xs text-gray-500 dark:text-gray-400">
                                                        <Loader2 className="mr-2 h-4 w-4 animate-spin text-blue-500" />
                                                        Loading batch executions...
                                                    </div>
                                                ) : children?.error ? (
                                                    <div className="px-3 py-3 text-xs text-red-600 dark:text-red-400">
                                                        {children.error}
                                                    </div>
                                                ) : (
                                                    <>
                                                        {(children?.executions || []).map((run, index) => (
                                                            <RunLogCard
                                                                key={run.id || run.execution_id || `${group.parent_execution_id}-${index}`}
                                                                run={run}
                                                                index={index}
                                                                {...cardProps}
                                                            />
                                                        ))}
                                                        {children?.hasMore && (
                                                            <div className="border-t border-indigo-200/80 px-3 py-2 dark:border-indigo-800/40">
                                                                <button
                                                                    type="button"
                                                                    onClick={() => void fetchGroupChildren(group.parent_execution_id, false)}
                                                                    disabled={children.loading}
                                                                    className="inline-flex items-center gap-1 rounded border border-gray-200 bg-white px-2 py-1 text-[10px] font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
                                                                >
                                                                    {children.loading && <Loader2 className="h-3 w-3 animate-spin" />}
                                                                    Load more
                                                                </button>
                                                            </div>
                                                        )}
                                                    </>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                );
                            })}

                            {hasMoreGroups && (
                                <div className="flex justify-center">
                                    <button
                                        type="button"
                                        onClick={() => void fetchQueueSummary(false)}
                                        disabled={loadingMoreGroups}
                                        className="inline-flex items-center gap-1 rounded border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
                                    >
                                        {loadingMoreGroups && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                                        Load more groups
                                    </button>
                                </div>
                            )}
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
