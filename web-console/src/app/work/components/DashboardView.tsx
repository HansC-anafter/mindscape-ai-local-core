'use client';

import { useState, useMemo } from 'react';
import { useDashboardSummary, useDashboardInbox, useDashboardCases, useDashboardAssignments } from '../hooks/useDashboard';
import type { DashboardQuery } from '../types';
import type { DashboardSelectedItem, DashboardTab } from './dashboardViewTypes';
import { AIFinderPanel, DetailPanel, SavedViewsPanel, SummaryPanel } from './dashboardViewPanels';
import { AssignmentsList, CasesList, InboxList } from './dashboardViewLists';

export function DashboardView() {
    const [activeTab, setActiveTab] = useState<DashboardTab>('inbox');
    const [scope, setScope] = useState('global');
    const [selectedItem, setSelectedItem] = useState<DashboardSelectedItem | null>(null);
    const [query, setQuery] = useState<DashboardQuery>({
        scope: 'global',
        limit: 50,
        offset: 0,
        sort_by: 'auto',
        sort_order: 'desc',
    });

    const scopedQuery = useMemo(() => ({ ...query, scope }), [query, scope]);

    const { data: summary, loading: summaryLoading, error: summaryError } = useDashboardSummary({
        scope,
        view: 'my_work',
    });

    const { data: inboxData, loading: inboxLoading, error: inboxError } = useDashboardInbox(scopedQuery);
    const { data: casesData, loading: casesLoading, error: casesError } = useDashboardCases(scopedQuery);
    const { data: assignmentsData, loading: assignmentsLoading, error: assignmentsError } = useDashboardAssignments(scopedQuery);

    return (
        <div className="flex h-full bg-white dark:bg-gray-900">
            <div className="w-72 border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-5 space-y-6 overflow-y-auto">
                <div className="space-y-2">
                    <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">視角</h2>
                    <select
                        value={scope === 'global' ? 'my_work' : scope}
                        onChange={(e) => setScope(e.target.value === 'my_work' ? 'global' : e.target.value)}
                        className="w-full rounded border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
                    >
                        <option value="my_work">我的工作</option>
                    </select>
                </div>

                <div className="space-y-2">
                    <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">範圍</h2>
                    <select
                        value={scope}
                        onChange={(e) => setScope(e.target.value)}
                        className="w-full rounded border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
                    >
                        <option value="global">Global</option>
                    </select>
                </div>

                <SavedViewsPanel
                    scope={scope}
                    activeTab={activeTab}
                    query={query}
                    onLoadView={(view) => {
                        setScope(view.scope);
                        setQuery({
                            ...query,
                            scope: view.scope,
                            view: view.view,
                            sort_by: view.sort_by,
                            sort_order: view.sort_order,
                            filters: view.filters,
                        });
                        if (view.tab) {
                            setActiveTab(view.tab as DashboardTab);
                        }
                    }}
                />

                <SummaryPanel summary={summary} loading={summaryLoading} error={summaryError} />
            </div>

            <div className="flex-1 flex bg-gray-50 dark:bg-gray-800">
                <div className="flex-1 flex flex-col">
                    <div className="flex items-center border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4">
                        {(['inbox', 'cases', 'assignments'] as const).map((tab) => (
                            <button
                                key={tab}
                                onClick={() => {
                                    setActiveTab(tab);
                                    setSelectedItem(null);
                                }}
                                className={`px-5 py-3 text-sm font-medium ${activeTab === tab
                                    ? 'border-b-2 border-blue-600 text-blue-600'
                                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                                    }`}
                            >
                                {tab.charAt(0).toUpperCase() + tab.slice(1)}
                            </button>
                        ))}
                        <div className="ml-auto flex items-center gap-2">
                            <select
                                value={query.sort_by || 'auto'}
                                onChange={(e) => setQuery({ ...query, sort_by: e.target.value })}
                                className="text-sm border border-gray-200 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                            >
                                <option value="auto">自動</option>
                                <option value="created_at">建立時間</option>
                                <option value="updated_at">更新時間</option>
                                <option value="status">狀態</option>
                            </select>
                            <select
                                value={query.sort_order || 'desc'}
                                onChange={(e) => setQuery({ ...query, sort_order: e.target.value })}
                                className="text-sm border border-gray-200 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                            >
                                <option value="desc">降序</option>
                                <option value="asc">升序</option>
                            </select>
                        </div>
                    </div>

                    <div className="flex-1 overflow-auto bg-gray-50 dark:bg-gray-800">
                        {activeTab === 'inbox' && (
                            <InboxList
                                data={inboxData}
                                loading={inboxLoading}
                                error={inboxError}
                                onSelect={(item) => setSelectedItem({ type: 'inbox', id: item.id, data: item })}
                                selectedId={selectedItem?.type === 'inbox' ? selectedItem.id : null}
                            />
                        )}
                        {activeTab === 'cases' && (
                            <CasesList
                                data={casesData}
                                loading={casesLoading}
                                error={casesError}
                                onSelect={(item) => setSelectedItem({ type: 'case', id: item.id, data: item })}
                                selectedId={selectedItem?.type === 'case' ? selectedItem.id : null}
                            />
                        )}
                        {activeTab === 'assignments' && (
                            <AssignmentsList
                                data={assignmentsData}
                                loading={assignmentsLoading}
                                error={assignmentsError}
                                onSelect={(item) => setSelectedItem({ type: 'assignment', id: item.id, data: item })}
                                selectedId={selectedItem?.type === 'assignment' ? selectedItem.id : null}
                            />
                        )}
                    </div>
                </div>

                <div className="w-[360px] border-l border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 flex flex-col">
                    {selectedItem ? (
                        <DetailPanel item={selectedItem} onClose={() => setSelectedItem(null)} />
                    ) : (
                        <AIFinderPanel />
                    )}
                </div>
            </div>
        </div>
    );
}
