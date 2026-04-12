/**
 * Run logs list component — supports batch grouping by parent_execution_id
 */
import React, { useState } from 'react';
import { ChevronRight } from 'lucide-react';
import type { RunInfo } from '../types';
import { parseTimestamp, formatRelativeTime } from '../utils/formatters';
import { RunLogCard } from './RunLogCard';

interface RunLogsListProps {
    workspaceId: string;
    recentRuns: RunInfo[];
    rerunBusyId: string | null;
    igRerunAllowPartial: boolean;
    canRerunStatus: (status: any) => boolean;
    rerunExecution: (executionId: string, overrideInputs?: Record<string, any>) => Promise<void>;
    isGlobalScope?: boolean;
    onToggleScope?: (scope: 'workspace' | 'global') => void;
}

/** Sort runs: running > pending/queued > failed > other, then by time desc */
function sortRuns(runs: RunInfo[]): RunInfo[] {
    return [...runs].sort((a, b) => {
        const getPrio = (r: any) => {
            const s = (r?.status || '').toString().toLowerCase();
            if (s === 'running') return 3;
            if (['pending', 'queued', 'paused'].includes(s)) return 2;
            if (s === 'failed') return 1;
            return 0;
        };
        const pa = getPrio(a);
        const pb = getPrio(b);
        if (pa !== pb) return pb - pa;

        const getTs = (r: any) => {
            const v = r?.created_at || r?.started_at || null;
            const d = parseTimestamp(v);
            return d ? d.getTime() : 0;
        };
        return getTs(b) - getTs(a);
    });
}

/** Summarise statuses for a batch group header */
function batchStatusSummary(runs: RunInfo[]): string {
    const counts: Record<string, number> = {};
    for (const r of runs) {
        const s = (r.status || 'unknown').toLowerCase();
        counts[s] = (counts[s] || 0) + 1;
    }
    return Object.entries(counts)
        .map(([s, n]) => `${n} ${s}`)
        .join(', ');
}

export function RunLogsList({
    workspaceId,
    recentRuns,
    rerunBusyId,
    igRerunAllowPartial,
    canRerunStatus,
    rerunExecution,
    isGlobalScope = false,
}: RunLogsListProps) {
    const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

    if (recentRuns.length === 0 && !isGlobalScope) {
        return (
            <div className="space-y-3">
                <p className="text-xs text-gray-500 dark:text-gray-400 text-center py-4">
                    No recent runs
                </p>
            </div>
        );
    }

    // Deduplicate runs by id
    const deduped = Array.from(
        new Map(recentRuns.map(r => [r.id || r.execution_id || crypto.randomUUID(), r])).values()
    );

    // Separate into grouped (have parent_execution_id) and ungrouped
    const groups = new Map<string, RunInfo[]>();
    const ungrouped: RunInfo[] = [];

    for (const run of deduped) {
        const parentId = run.parent_execution_id || run.execution_context?.parent_execution_id;
        if (parentId && typeof parentId === 'string') {
            const list = groups.get(parentId) || [];
            list.push(run);
            groups.set(parentId, list);
        } else {
            ungrouped.push(run);
        }
    }

    // Sort each group's children and the ungrouped list
    const sortedUngrouped = sortRuns(ungrouped);

    // Build render items: interleave groups and ungrouped by earliest created_at
    type RenderItem =
        | { type: 'single'; run: RunInfo }
        | { type: 'group'; parentId: string; runs: RunInfo[] };

    const items: RenderItem[] = [];
    for (const run of sortedUngrouped) {
        items.push({ type: 'single', run });
    }
    for (const [parentId, runs] of groups) {
        items.push({ type: 'group', parentId, runs: sortRuns(runs) });
    }

    // Sort all render items by sort key (running > pending > failed > other, then time desc)
    items.sort((a, b) => {
        const getPrio = (r: RunInfo) => {
            const s = (r?.status || '').toString().toLowerCase();
            if (s === 'running') return 3;
            if (['pending', 'queued', 'paused'].includes(s)) return 2;
            if (s === 'failed') return 1;
            return 0;
        };
        const getTs = (r: RunInfo) => {
            const v = r?.created_at || r?.started_at || null;
            const d = parseTimestamp(v);
            return d ? d.getTime() : 0;
        };

        // For groups, use the highest-priority / newest child as representative
        const repA = a.type === 'single' ? a.run : a.runs[0];
        const repB = b.type === 'single' ? b.run : b.runs[0];
        const pa = getPrio(repA);
        const pb = getPrio(repB);
        if (pa !== pb) return pb - pa;
        return getTs(repB) - getTs(repA);
    });

    const toggleGroup = (parentId: string) => {
        setExpandedGroups(prev => {
            const next = new Set(prev);
            if (next.has(parentId)) next.delete(parentId);
            else next.add(parentId);
            return next;
        });
    };

    const cardProps = { workspaceId, rerunBusyId, igRerunAllowPartial, canRerunStatus, rerunExecution };

    return (
        <div className="space-y-3">
            {items.length === 0 ? (
                <p className="text-xs text-gray-500 dark:text-gray-400 text-center py-4">
                    No runs found
                </p>
            ) : (
                <div className="space-y-2">
                    {items.map((item, idx) => {
                        if (item.type === 'single') {
                            return (
                                <RunLogCard
                                    key={item.run.id || item.run.execution_id || `run-${idx}`}
                                    run={item.run}
                                    index={idx}
                                    {...cardProps}
                                />
                            );
                        }

                        // Group block
                        const { parentId, runs } = item;
                        const isExpanded = expandedGroups.has(parentId);
                        const sourceHandle =
                            runs[0]?.execution_context?.inputs?.source_handle ||
                            runs[0]?.execution_context?.inputs?.target_handle ||
                            '';
                        const playbookLabel = (runs[0]?.playbook_code || '').replace('ig_', '').replace(/_/g, ' ');

                        return (
                            <div
                                key={`group-${parentId}`}
                                className="border border-indigo-200 dark:border-indigo-800/50 rounded-lg overflow-hidden bg-indigo-50/30 dark:bg-indigo-900/10"
                            >
                                {/* Group Header */}
                                <button
                                    type="button"
                                    onClick={() => toggleGroup(parentId)}
                                    className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-indigo-100/50 dark:hover:bg-indigo-900/20 transition-colors"
                                >
                                    <ChevronRight
                                        className={`w-3.5 h-3.5 text-indigo-500 shrink-0 transition-transform duration-150 ${isExpanded ? 'rotate-90' : ''}`}
                                    />
                                    <div className="flex-1 min-w-0">
                                        <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-400">
                                            Batch{sourceHandle ? ` · ${sourceHandle}` : ''}
                                        </span>
                                        <span className="text-[10px] text-gray-500 dark:text-gray-400 ml-2">
                                            {runs.length} tasks · {batchStatusSummary(runs)}
                                        </span>
                                    </div>
                                    <span
                                        className="text-[9px] text-gray-400 dark:text-gray-500 font-mono shrink-0 cursor-pointer hover:text-gray-600"
                                        title={`Parent: ${parentId}`}
                                        onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(parentId); }}
                                    >
                                        {parentId.slice(0, 8)}…
                                    </span>
                                </button>

                                {/* Expanded children */}
                                {isExpanded && (
                                    <div className="border-t border-indigo-200 dark:border-indigo-800/50">
                                        {runs.map((run, childIdx) => (
                                            <RunLogCard
                                                key={run.id || run.execution_id || `group-${parentId}-${childIdx}`}
                                                run={run}
                                                index={childIdx}
                                                {...cardProps}
                                            />
                                        ))}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
