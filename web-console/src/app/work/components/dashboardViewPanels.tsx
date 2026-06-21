'use client';

import { useState } from 'react';
import { useSavedViews } from '../hooks/useSavedViews';
import type { DashboardQuery, SavedViewDTO } from '../types';
import type { DashboardSelectedItem, DashboardTab } from './dashboardViewTypes';

export function SavedViewsPanel({
    scope,
    activeTab,
    query,
    onLoadView,
}: {
    scope: string;
    activeTab: DashboardTab;
    query: DashboardQuery;
    onLoadView: (view: SavedViewDTO) => void;
}) {
    const { views, loading, createView, deleteView } = useSavedViews();
    const [showSaveDialog, setShowSaveDialog] = useState(false);
    const [viewName, setViewName] = useState('');

    const handleSaveView = async () => {
        if (!viewName.trim()) return;

        await createView({
            name: viewName,
            scope,
            view: query.view || 'my_work',
            tab: activeTab,
            filters: query.filters || {},
            sort_by: query.sort_by || 'auto',
            sort_order: query.sort_order || 'desc',
        });

        setViewName('');
        setShowSaveDialog(false);
    };

    return (
        <div className="space-y-3">
            <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">已儲存的視角</h2>
                <button
                    onClick={() => setShowSaveDialog(true)}
                    className="text-xs text-blue-600 hover:text-blue-800"
                >
                    + 儲存
                </button>
            </div>

            {showSaveDialog && (
                <div className="mb-2 p-2 border border-gray-200 dark:border-gray-600 rounded bg-white dark:bg-gray-800 shadow-sm">
                    <input
                        type="text"
                        value={viewName}
                        onChange={(e) => setViewName(e.target.value)}
                        placeholder="視角名稱"
                        className="w-full p-1 border border-gray-200 dark:border-gray-600 rounded text-sm mb-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                        onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                                handleSaveView();
                            } else if (e.key === 'Escape') {
                                setShowSaveDialog(false);
                            }
                        }}
                        autoFocus
                    />
                    <div className="flex gap-2">
                        <button
                            onClick={handleSaveView}
                            className="flex-1 px-2 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
                        >
                            儲存
                        </button>
                        <button
                            onClick={() => {
                                setShowSaveDialog(false);
                                setViewName('');
                            }}
                            className="flex-1 px-2 py-1 text-sm border border-gray-200 dark:border-gray-600 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100"
                        >
                            取消
                        </button>
                    </div>
                </div>
            )}

            {loading ? (
                <div className="text-sm text-gray-500">Loading...</div>
            ) : views.length === 0 ? (
                <div className="text-sm text-gray-500">No saved views</div>
            ) : (
                <div className="space-y-1 max-h-48 overflow-auto pr-1">
                    {views.map((view) => (
                        <div
                            key={view.id}
                            className="flex items-center justify-between p-2 border border-gray-200 dark:border-gray-600 rounded hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer group"
                            onClick={() => onLoadView(view)}
                        >
                            <span className="text-sm text-gray-900 dark:text-gray-100">{view.name}</span>
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    if (confirm(`Delete "${view.name}"?`)) {
                                        deleteView(view.id);
                                    }
                                }}
                                className="opacity-0 group-hover:opacity-100 text-red-600 hover:text-red-800 text-xs"
                            >
                                ×
                            </button>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

export function SummaryPanel({
    summary,
    loading,
    error,
}: {
    summary: any;
    loading: boolean;
    error: Error | null;
}) {
    if (loading) {
        return <div className="text-sm text-gray-500">Loading summary...</div>;
    }

    if (error) {
        return (
            <div
                className={`text-sm p-3 rounded ${(error as any)?.isAuthError
                    ? 'bg-red-50 border border-red-200 text-red-800'
                    : 'bg-yellow-50 border border-yellow-200 text-yellow-800'
                    }`}
            >
                <p className="font-semibold mb-1">
                    {(error as any)?.status === 401
                        ? 'Authentication Required'
                        : (error as any)?.status === 403
                            ? 'Access Denied'
                            : 'Error'}
                </p>
                <p>{error.message}</p>
            </div>
        );
    }

    if (!summary) return null;

    return (
        <div className="space-y-3">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">統計</h2>
            <div className="grid grid-cols-2 gap-2 text-sm">
                <Stat label="Open Cases" value={summary.counts.open_cases} />
                <Stat label="Open Assignments" value={summary.counts.open_assignments} />
                <Stat label="Blocked Cases" value={summary.counts.blocked_cases} />
                <Stat label="Running Jobs" value={summary.counts.running_jobs} />
            </div>
            {summary.not_supported.length > 0 && (
                <div className="p-2 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-800">
                    <p className="font-semibold">Not Supported</p>
                    <ul className="list-disc list-inside">
                        {summary.not_supported.map((item: string) => (
                            <li key={item}>{item}</li>
                        ))}
                    </ul>
                </div>
            )}
            {summary.warnings.length > 0 && (
                <div className="p-2 bg-blue-50 border border-blue-200 rounded text-xs text-blue-800">
                    <p className="font-semibold">Warnings</p>
                    <ul className="list-disc list-inside">
                        {summary.warnings.map((warning: string, idx: number) => (
                            <li key={idx}>{warning}</li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
}

function Stat({ label, value }: { label: string; value: number }) {
    return (
        <div className="flex flex-col rounded border border-gray-100 dark:border-gray-700 p-2">
            <span className="text-xs text-gray-500 dark:text-gray-400">{label}</span>
            <span className="text-base font-semibold text-gray-900 dark:text-gray-100">{value}</span>
        </div>
    );
}

export function AIFinderPanel() {
    return (
        <div className="flex-1 p-6 bg-white dark:bg-gray-900 flex flex-col">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">AI Finder</h3>
                <span className="text-xs text-gray-500 dark:text-gray-400">實驗功能</span>
            </div>
            <div className="flex-1 rounded border border-dashed border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 p-4 text-center flex flex-col items-center justify-center">
                <p className="text-sm text-gray-700 dark:text-gray-300 font-medium mb-2">AI-powered search and insights</p>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">Select an item to view details or use AI Finder to search</p>
                <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 text-blue-800 dark:text-blue-300 text-xs px-3 py-2 rounded">
                    Note:
                    <br />
                    AI Finder is a placeholder. Full implementation pending.
                </div>
            </div>
        </div>
    );
}

export function DetailPanel({
    item,
    onClose,
}: {
    item: DashboardSelectedItem;
    onClose: () => void;
}) {
    return (
        <div className="flex-1 p-6 bg-white dark:bg-gray-900 flex flex-col">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Details</h3>
                <button onClick={onClose} className="text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
                    Close
                </button>
            </div>
            <div className="flex-1 overflow-auto rounded border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 p-4 text-sm">
                <pre className="whitespace-pre-wrap break-words text-gray-800 dark:text-gray-200">{JSON.stringify(item.data, null, 2)}</pre>
            </div>
        </div>
    );
}
