'use client';

import { useState } from 'react';
import { useDashboardSummary, useDashboardInbox, useDashboardCases, useDashboardAssignments } from './hooks/useDashboard';
import { useSavedViews } from './hooks/useSavedViews';
import type { DashboardQuery, SavedViewDTO } from './types';

export default function WorkPage() {
  const [activeTab, setActiveTab] = useState<'inbox' | 'cases' | 'assignments'>('inbox');
  const [scope, setScope] = useState('global');
  const [selectedItem, setSelectedItem] = useState<{
    type: 'inbox' | 'case' | 'assignment';
    id: string;
    data: any;
  } | null>(null);
  const [query, setQuery] = useState<DashboardQuery>({
    scope: 'global',
    limit: 50,
    offset: 0,
    sort_by: 'auto',
    sort_order: 'desc',
  });

  const { data: summary, loading: summaryLoading, error: summaryError } = useDashboardSummary({
    scope,
    view: 'my_work',
  });

  const { data: inboxData, loading: inboxLoading, error: inboxError } = useDashboardInbox({
    ...query,
    scope,
  });

  const { data: casesData, loading: casesLoading, error: casesError } = useDashboardCases({
    ...query,
    scope,
  });

  const { data: assignmentsData, loading: assignmentsLoading, error: assignmentsError } = useDashboardAssignments({
    ...query,
    scope,
  });

  return (
    <div className="flex h-screen bg-white">
      {/* Left Sidebar */}
      <div className="w-72 border-r bg-white px-4 py-5 space-y-6 overflow-y-auto">
        <div className="space-y-2">
          <h2 className="text-sm font-semibold text-gray-900">視角</h2>
          <select
            value={scope === 'global' ? 'my_work' : scope}
            onChange={(e) => setScope(e.target.value === 'my_work' ? 'global' : e.target.value)}
            className="w-full rounded border border-gray-200 px-3 py-2 text-sm"
          >
            <option value="my_work">我的工作</option>
          </select>
        </div>

        <div className="space-y-2">
          <h2 className="text-sm font-semibold text-gray-900">範圍</h2>
          <select
            value={scope}
            onChange={(e) => setScope(e.target.value)}
            className="w-full rounded border border-gray-200 px-3 py-2 text-sm"
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
              setActiveTab(view.tab as 'inbox' | 'cases' | 'assignments');
            }
          }}
        />

        <SummaryPanel summary={summary} loading={summaryLoading} error={summaryError} />
      </div>

      {/* Middle + Right */}
      <div className="flex-1 flex bg-gray-50">
        {/* Middle Column */}
        <div className="flex-1 flex flex-col">
          <div className="flex items-center border-b bg-white px-4">
            {(['inbox', 'cases', 'assignments'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => {
                  setActiveTab(tab);
                  setSelectedItem(null);
                }}
                className={`px-5 py-3 text-sm font-medium ${
                  activeTab === tab
                    ? 'border-b-2 border-blue-600 text-blue-600'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </button>
            ))}
            <div className="ml-auto flex items-center gap-2">
              <select
                value={query.sort_by || 'auto'}
                onChange={(e) => setQuery({ ...query, sort_by: e.target.value })}
                className="text-sm border border-gray-200 rounded px-2 py-1 bg-white"
              >
                <option value="auto">自動</option>
                <option value="created_at">建立時間</option>
                <option value="updated_at">更新時間</option>
                <option value="status">狀態</option>
              </select>
              <select
                value={query.sort_order || 'desc'}
                onChange={(e) => setQuery({ ...query, sort_order: e.target.value })}
                className="text-sm border border-gray-200 rounded px-2 py-1 bg-white"
              >
                <option value="desc">降序</option>
                <option value="asc">升序</option>
              </select>
            </div>
          </div>

          <div className="flex-1 overflow-auto bg-gray-50">
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

        {/* Right Column */}
        <div className="w-[360px] border-l bg-white flex flex-col">
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

function SavedViewsPanel({
  scope,
  activeTab,
  query,
  onLoadView,
}: {
  scope: string;
  activeTab: 'inbox' | 'cases' | 'assignments';
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
        <h2 className="text-sm font-semibold text-gray-900">已儲存的視角</h2>
        <button
          onClick={() => setShowSaveDialog(true)}
          className="text-xs text-blue-600 hover:text-blue-800"
        >
          + 儲存
        </button>
      </div>

      {showSaveDialog && (
        <div className="mb-2 p-2 border rounded bg-white shadow-sm">
          <input
            type="text"
            value={viewName}
            onChange={(e) => setViewName(e.target.value)}
            placeholder="視角名稱"
            className="w-full p-1 border rounded text-sm mb-2"
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
              className="flex-1 px-2 py-1 text-sm border rounded hover:bg-gray-100"
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
              className="flex items-center justify-between p-2 border rounded hover:bg-gray-100 cursor-pointer group"
              onClick={() => onLoadView(view)}
            >
              <span className="text-sm">{view.name}</span>
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

function SummaryPanel({
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
        className={`text-sm p-3 rounded ${
          (error as any)?.isAuthError
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
      <h2 className="text-sm font-semibold text-gray-900">統計</h2>
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
    <div className="flex flex-col rounded border border-gray-100 p-2">
      <span className="text-xs text-gray-500">{label}</span>
      <span className="text-base font-semibold text-gray-900">{value}</span>
    </div>
  );
}

function InboxList({
  data,
  loading,
  error,
  onSelect,
  selectedId,
}: {
  data: any;
  loading: boolean;
  error: Error | null;
  onSelect: (item: any) => void;
  selectedId: string | null;
}) {
  if (loading) {
    return <div className="p-8 text-center text-gray-500">Loading inbox...</div>;
  }

  if (error) {
    return (
      <div
        className={`p-6 m-4 rounded ${
          (error as any)?.isAuthError
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

  if (!data) {
    return <div className="p-8 text-center text-gray-500">No data</div>;
  }

  if (data.items.length === 0) {
    return <div className="p-8 text-center text-gray-500">No inbox items</div>;
  }

  return (
    <div className="divide-y">
      {data.items.map((item: any) => (
        <div
          key={item.id}
          onClick={() => onSelect(item)}
          className={`p-4 cursor-pointer hover:bg-gray-50 ${
            selectedId === item.id ? 'bg-blue-50 border-l-4 border-blue-500' : ''
          }`}
        >
          <h3 className="font-semibold">{item.title}</h3>
          {item.summary && <p className="text-sm text-gray-600 mt-1 line-clamp-2">{item.summary}</p>}
          <div className="mt-2 text-xs text-gray-500">
            {item.workspace_name && <span>{item.workspace_name} • </span>}
            {item.due_at ? (
              <span>Due: {new Date(item.due_at).toLocaleDateString()}</span>
            ) : (
              <span className="text-gray-400 italic">Due date not supported in Local-Core</span>
            )}
          </div>
        </div>
      ))}
      {data.warnings.length > 0 && (
        <div className="p-4 bg-yellow-50 border-t border-yellow-200 text-sm">
          <p className="font-semibold text-yellow-800 mb-1">Note:</p>
          <ul className="list-disc list-inside text-yellow-700 space-y-1">
            {data.warnings.map((warning: string, idx: number) => (
              <li key={idx}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
      {data.has_more && (
        <div className="p-4 text-center border-t">
          <button className="text-sm text-blue-600 hover:text-blue-800" onClick={() => {}}>
            Load more...
          </button>
        </div>
      )}
    </div>
  );
}

function CasesList({
  data,
  loading,
  error,
  onSelect,
  selectedId,
}: {
  data: any;
  loading: boolean;
  error: Error | null;
  onSelect: (item: any) => void;
  selectedId: string | null;
}) {
  if (loading) {
    return <div className="p-8 text-center text-gray-500">Loading cases...</div>;
  }

  if (error) {
    return (
      <div
        className={`p-6 m-4 rounded ${
          (error as any)?.isAuthError
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

  if (!data) {
    return <div className="p-8 text-center text-gray-500">No data</div>;
  }

  if (data.items.length === 0) {
    return <div className="p-8 text-center text-gray-500">No cases</div>;
  }

  return (
    <div className="divide-y">
      {data.items.map((caseItem: any) => (
        <div
          key={caseItem.id}
          onClick={() => onSelect(caseItem)}
          className={`p-4 cursor-pointer hover:bg-gray-50 ${
            selectedId === caseItem.id ? 'bg-blue-50 border-l-4 border-blue-500' : ''
          }`}
        >
          <h3 className="font-semibold">{caseItem.title || 'Untitled Case'}</h3>
          {caseItem.summary && <p className="text-sm text-gray-600 mt-1 line-clamp-2">{caseItem.summary}</p>}
          <div className="mt-2 flex items-center gap-4 text-xs text-gray-500">
            <span
              className={`px-2 py-1 rounded ${
                caseItem.status === 'blocked'
                  ? 'bg-red-100 text-red-800'
                  : caseItem.status === 'completed'
                  ? 'bg-green-100 text-green-800'
                  : 'bg-blue-100 text-blue-800'
              }`}
            >
              {caseItem.status}
            </span>
            {caseItem.progress_percent !== undefined && <span>Progress: {caseItem.progress_percent}%</span>}
            {caseItem.workspace_name && <span>{caseItem.workspace_name}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

function AssignmentsList({
  data,
  loading,
  error,
  onSelect,
  selectedId,
}: {
  data: any;
  loading: boolean;
  error: Error | null;
  onSelect: (item: any) => void;
  selectedId: string | null;
}) {
  if (loading) {
    return <div className="p-8 text-center text-gray-500">Loading assignments...</div>;
  }

  if (error) {
    return (
      <div
        className={`p-6 m-4 rounded ${
          (error as any)?.isAuthError
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

  if (!data) {
    return <div className="p-8 text-center text-gray-500">No data</div>;
  }

  if (data.items.length === 0) {
    return <div className="p-8 text-center text-gray-500">No assignments</div>;
  }

  return (
    <div className="divide-y">
      {data.items.map((assignment: any) => (
        <div
          key={assignment.id}
          onClick={() => onSelect(assignment)}
          className={`p-4 cursor-pointer hover:bg-gray-50 ${
            selectedId === assignment.id ? 'bg-blue-50 border-l-4 border-blue-500' : ''
          }`}
        >
          <h3 className="font-semibold">{assignment.title}</h3>
          {assignment.description && (
            <p className="text-sm text-gray-600 mt-1 line-clamp-2">{assignment.description}</p>
          )}
          <div className="mt-2 flex items-center gap-4 text-xs text-gray-500">
            <span
              className={`px-2 py-1 rounded ${
                assignment.status === 'pending'
                  ? 'bg-yellow-100 text-yellow-800'
                  : assignment.status === 'completed'
                  ? 'bg-green-100 text-green-800'
                  : assignment.status === 'failed'
                  ? 'bg-red-100 text-red-800'
                  : 'bg-blue-100 text-blue-800'
              }`}
            >
              {assignment.status}
            </span>
            {assignment.due_at ? (
              <span>Due: {new Date(assignment.due_at).toLocaleDateString()}</span>
            ) : (
              <span className="text-gray-400 italic">Due date not supported in Local-Core</span>
            )}
            {assignment.target_workspace_name && <span>{assignment.target_workspace_name}</span>}
          </div>
        </div>
      ))}
      {data.warnings.length > 0 && (
        <div className="p-4 bg-yellow-50 border-t border-yellow-200 text-sm">
          <p className="font-semibold text-yellow-800 mb-1">Note:</p>
          <ul className="list-disc list-inside text-yellow-700 space-y-1">
            {data.warnings.map((warning: string, idx: number) => (
              <li key={idx}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function AIFinderPanel() {
  return (
    <div className="flex-1 p-6 bg-white flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">AI Finder</h3>
        <span className="text-xs text-gray-500">實驗功能</span>
      </div>
      <div className="flex-1 rounded border border-dashed border-gray-200 bg-gray-50 p-4 text-center flex flex-col items-center justify-center">
        <p className="text-sm text-gray-700 font-medium mb-2">AI-powered search and insights</p>
        <p className="text-xs text-gray-500 mb-4">Select an item to view details or use AI Finder to search</p>
        <div className="bg-blue-50 border border-blue-200 text-blue-800 text-xs px-3 py-2 rounded">
          Note:
          <br />
          AI Finder is a placeholder. Full implementation pending.
        </div>
      </div>
    </div>
  );
}

function DetailPanel({
  item,
  onClose,
}: {
  item: { type: 'inbox' | 'case' | 'assignment'; id: string; data: any };
  onClose: () => void;
}) {
  return (
    <div className="flex-1 p-6 bg-white flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-900">Details</h3>
        <button onClick={onClose} className="text-sm text-gray-500 hover:text-gray-700">
          Close
        </button>
      </div>
      <div className="flex-1 overflow-auto rounded border border-gray-200 bg-gray-50 p-4 text-sm">
        <pre className="whitespace-pre-wrap break-words text-gray-800">{JSON.stringify(item.data, null, 2)}</pre>
      </div>
    </div>
  );
}
