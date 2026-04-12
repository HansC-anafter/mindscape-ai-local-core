import React, { useState } from 'react';
import { ChevronRight } from 'lucide-react';
import type { RunInfo } from '../types';
import { parseTimestamp } from '../utils/formatters';
import { RunLogCard } from './RunLogCard';

interface GroupSummary {
    total: number;
    succeeded: number;
    failed: number;
    running: number;
    pending: number;
}

interface ServerRunGroup {
    parent_execution_id: string;
    tasks: RunInfo[];
    summary: GroupSummary;
}

interface GroupedRunLogsListProps {
    workspaceId: string;
    recentGroups: ServerRunGroup[];
    ungroupedRuns: RunInfo[];
    rerunBusyId: string | null;
    igRerunAllowPartial: boolean;
    canRerunStatus: (status: any) => boolean;
    rerunExecution: (executionId: string, overrideInputs?: Record<string, any>) => Promise<void>;
}

export function GroupedRunLogsList({
    workspaceId,
    recentGroups,
    ungroupedRuns,
    rerunBusyId,
    igRerunAllowPartial,
    canRerunStatus,
    rerunExecution,
}: GroupedRunLogsListProps) {
    const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

    if (recentGroups.length === 0 && ungroupedRuns.length === 0) {
        return (
            <div className="space-y-3">
                <p className="text-xs text-gray-500 dark:text-gray-400 text-center py-4">
                    No recent runs
                </p>
            </div>
        );
    }

    type RenderItem =
        | { type: 'single'; run: RunInfo; ts: number }
        | { type: 'group'; group: ServerRunGroup; ts: number };

    const items: RenderItem[] = [];

    const getTs = (r: RunInfo) => {
        const v = r?.created_at || r?.started_at || null;
        const d = parseTimestamp(v);
        return d ? d.getTime() : 0;
    };

    for (const run of ungroupedRuns) {
        items.push({ type: 'single', run, ts: getTs(run) });
    }

    for (const group of recentGroups) {
        const latestTs = Math.max(...group.tasks.map(getTs), 0);
        items.push({ type: 'group', group, ts: latestTs });
    }

    items.sort((a, b) => b.ts - a.ts);

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

                const { parent_execution_id, tasks, summary } = item.group;
                const isExpanded = expandedGroups.has(parent_execution_id);
                const sourceHandle =
                    tasks[0]?.execution_context?.inputs?.source_handle ||
                    tasks[0]?.execution_context?.inputs?.target_handle ||
                    '';
                
                // Sort tasks inside group by time descending
                const sortedTasks = [...tasks].sort((a, b) => getTs(b) - getTs(a));

                return (
                    <div
                        key={`group-${parent_execution_id}`}
                        className="border border-indigo-200 dark:border-indigo-800/50 rounded-lg overflow-hidden bg-indigo-50/30 dark:bg-indigo-900/10"
                    >
                        <button
                            type="button"
                            onClick={() => toggleGroup(parent_execution_id)}
                            className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-indigo-100/50 dark:hover:bg-indigo-900/20 transition-colors"
                        >
                            <ChevronRight
                                className={`w-3.5 h-3.5 text-indigo-500 shrink-0 transition-transform duration-150 ${isExpanded ? 'rotate-90' : ''}`}
                            />
                            <div className="flex-1 min-w-0">
                                <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-400">
                                    Batch Group{sourceHandle ? ` · ${sourceHandle}` : ''}
                                </span>
                                <span className="text-[10px] text-gray-500 dark:text-gray-400 ml-2">
                                    {summary.total} tasks 
                                    {summary.running > 0 && ` · ${summary.running} running`}
                                    {summary.pending > 0 && ` · ${summary.pending} pending`}
                                    {summary.failed > 0 && ` · ${summary.failed} failed`}
                                    {summary.succeeded > 0 && ` · ${summary.succeeded} completed`}
                                </span>
                            </div>
                            <span
                                className="text-[9px] text-gray-400 dark:text-gray-500 font-mono shrink-0 cursor-pointer hover:text-gray-600"
                                title={`Parent: ${parent_execution_id}`}
                                onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(parent_execution_id); }}
                            >
                                {parent_execution_id.slice(0, 8)}…
                            </span>
                        </button>

                        {isExpanded && (
                            <div className="border-t border-indigo-200 dark:border-indigo-800/50">
                                {sortedTasks.map((run, childIdx) => (
                                    <RunLogCard
                                        key={run.id || run.execution_id || `group-${parent_execution_id}-${childIdx}`}
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
    );
}
