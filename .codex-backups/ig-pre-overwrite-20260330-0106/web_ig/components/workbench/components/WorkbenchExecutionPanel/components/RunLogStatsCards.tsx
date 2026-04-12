import React from 'react';

import type { RunLogCounts } from '../types';

interface RunLogStatsCardsProps {
    counts: RunLogCounts;
    targetsTotal: number | null;
    activeRunCount: number;
}

const STAT_ITEMS: Array<{
    key: keyof RunLogCounts;
    label: string;
    accent: string;
}> = [
    { key: 'completed', label: '✅ Completed', accent: 'text-green-600 dark:text-green-400' },
    { key: 'running', label: '▶ Running', accent: 'text-sky-600 dark:text-sky-400' },
    { key: 'pending', label: '⏳ Pending', accent: 'text-amber-600 dark:text-amber-400' },
    { key: 'failed', label: '❌ Failed', accent: 'text-red-600 dark:text-red-400' },
];

export function RunLogStatsCards({ counts, targetsTotal, activeRunCount }: RunLogStatsCardsProps) {
    return (
        <div className="mb-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/40 px-3 py-2">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                Backlog
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2">
                <div className="rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-3">
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                        Reference
                    </div>
                    <div className="mt-1 text-2xl font-semibold text-gray-900 dark:text-gray-100 tabular-nums">
                        {counts.total}
                    </div>
                </div>
                <div className="rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-3">
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                        Targets
                    </div>
                    <div className="mt-1 text-2xl font-semibold text-violet-600 dark:text-violet-400 tabular-nums">
                        {targetsTotal ?? '—'}
                    </div>
                </div>
                {STAT_ITEMS.map((item) => (
                    <div
                        key={item.key}
                        className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2"
                    >
                        <div className="text-[10px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                            {item.label}
                        </div>
                        <div className={`mt-1 text-base font-semibold tabular-nums ${item.accent}`}>
                            {counts[item.key]}
                        </div>
                    </div>
                ))}
                <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2">
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                        ▶ Active Runs
                    </div>
                    <div className="mt-1 text-base font-semibold text-sky-600 dark:text-sky-400 tabular-nums">
                        {activeRunCount}
                    </div>
                </div>
            </div>
        </div>
    );
}
