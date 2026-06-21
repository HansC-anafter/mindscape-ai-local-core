import { formatLocalDateTime } from '@/lib/time';

export function InboxList({
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
        return <DashboardError error={error} />;
    }

    if (!data) {
        return <div className="p-8 text-center text-gray-500">No data</div>;
    }

    if (data.items.length === 0) {
        return <div className="p-8 text-center text-gray-500">No inbox items</div>;
    }

    return (
        <div className="divide-y divide-gray-200 dark:divide-gray-700">
            {data.items.map((item: any) => (
                <div
                    key={item.id}
                    onClick={() => onSelect(item)}
                    className={`p-4 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 ${selectedId === item.id ? 'bg-blue-50 dark:bg-blue-900/20 border-l-4 border-blue-500' : ''
                        }`}
                >
                    <h3 className="font-semibold text-gray-900 dark:text-gray-100">{item.title}</h3>
                    {item.summary && <p className="text-sm text-gray-600 dark:text-gray-400 mt-1 line-clamp-2">{item.summary}</p>}
                    <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                        {item.workspace_name && <span>{item.workspace_name} • </span>}
                        {item.due_at ? (
                            <span>Due: {formatLocalDateTime(item.due_at)}</span>
                        ) : (
                            <span className="text-gray-400 italic">Due date not supported in Local-Core</span>
                        )}
                    </div>
                </div>
            ))}
            <Warnings warnings={data.warnings} />
            {data.has_more && (
                <div className="p-4 text-center border-t border-gray-200 dark:border-gray-700">
                    <button className="text-sm text-blue-600 hover:text-blue-800" onClick={() => { }}>
                        Load more...
                    </button>
                </div>
            )}
        </div>
    );
}

export function CasesList({
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
        return <DashboardError error={error} />;
    }

    if (!data) {
        return <div className="p-8 text-center text-gray-500">No data</div>;
    }

    if (data.items.length === 0) {
        return <div className="p-8 text-center text-gray-500">No cases</div>;
    }

    return (
        <div className="divide-y divide-gray-200 dark:divide-gray-700">
            {data.items.map((caseItem: any) => (
                <div
                    key={caseItem.id}
                    onClick={() => onSelect(caseItem)}
                    className={`p-4 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 ${selectedId === caseItem.id ? 'bg-blue-50 dark:bg-blue-900/20 border-l-4 border-blue-500' : ''
                        }`}
                >
                    <h3 className="font-semibold text-gray-900 dark:text-gray-100">{caseItem.title || 'Untitled Case'}</h3>
                    {caseItem.summary && <p className="text-sm text-gray-600 dark:text-gray-400 mt-1 line-clamp-2">{caseItem.summary}</p>}
                    <div className="mt-2 flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                        <span
                            className={`px-2 py-1 rounded ${caseItem.status === 'blocked'
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

export function AssignmentsList({
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
        return <DashboardError error={error} />;
    }

    if (!data) {
        return <div className="p-8 text-center text-gray-500">No data</div>;
    }

    if (data.items.length === 0) {
        return <div className="p-8 text-center text-gray-500">No assignments</div>;
    }

    return (
        <div className="divide-y divide-gray-200 dark:divide-gray-700">
            {data.items.map((assignment: any) => (
                <div
                    key={assignment.id}
                    onClick={() => onSelect(assignment)}
                    className={`p-4 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 ${selectedId === assignment.id ? 'bg-blue-50 dark:bg-blue-900/20 border-l-4 border-blue-500' : ''
                        }`}
                >
                    <h3 className="font-semibold text-gray-900 dark:text-gray-100">{assignment.title}</h3>
                    {assignment.description && (
                        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1 line-clamp-2">{assignment.description}</p>
                    )}
                    <div className="mt-2 flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                        <span
                            className={`px-2 py-1 rounded ${assignment.status === 'pending'
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
                            <span>Due: {formatLocalDateTime(assignment.due_at)}</span>
                        ) : (
                            <span className="text-gray-400 italic">Due date not supported in Local-Core</span>
                        )}
                        {assignment.target_workspace_name && <span>{assignment.target_workspace_name}</span>}
                    </div>
                </div>
            ))}
            <Warnings warnings={data.warnings} />
        </div>
    );
}

function DashboardError({ error }: { error: Error }) {
    return (
        <div
            className={`p-6 m-4 rounded ${(error as any)?.isAuthError
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

function Warnings({ warnings }: { warnings: string[] }) {
    if (warnings.length === 0) return null;

    return (
        <div className="p-4 bg-yellow-50 border-t border-yellow-200 text-sm">
            <p className="font-semibold text-yellow-800 mb-1">Note:</p>
            <ul className="list-disc list-inside text-yellow-700 space-y-1">
                {warnings.map((warning: string, idx: number) => (
                    <li key={idx}>{warning}</li>
                ))}
            </ul>
        </div>
    );
}
