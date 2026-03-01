'use client';

import React, { useState, useEffect } from 'react';

interface WorkspaceGroupMember {
    workspace_id: string;
    role: string;
    title?: string | null;
    visibility?: string | null;
    joined_at?: string | null;
}

interface WorkspaceGroupData {
    id: string;
    display_name: string;
    members: WorkspaceGroupMember[];
}

interface WorkspaceGroupIndicatorProps {
    groupId: string;
    workspaceRole?: string | null;
    apiUrl: string;
}

/**
 * Shows group membership indicator with a modal
 * that fetches real group topology from the API.
 */
export default function WorkspaceGroupIndicator({
    groupId,
    workspaceRole,
    apiUrl,
}: WorkspaceGroupIndicatorProps) {
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [groupData, setGroupData] = useState<WorkspaceGroupData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Fetch group data when modal opens
    useEffect(() => {
        if (!isModalOpen) return;

        const fetchGroupData = async () => {
            setLoading(true);
            setError(null);
            try {
                const res = await fetch(`${apiUrl}/api/v1/workspace-groups/${groupId}`);
                if (res.ok) {
                    const data = await res.json();
                    setGroupData(data);
                } else if (res.status === 404) {
                    setError('Group not found');
                } else {
                    setError(`Failed to load (${res.status})`);
                }
            } catch (err) {
                console.error('[WorkspaceGroupIndicator] Error fetching group:', err);
                setError('Network error');
            } finally {
                setLoading(false);
            }
        };

        fetchGroupData();
    }, [isModalOpen, groupId, apiUrl]);

    const roleIcon = (role: string) => {
        switch (role) {
            case 'dispatch': return '🎯';
            case 'cell': return '🔬';
            default: return '📦';
        }
    };

    const roleColor = (role: string) => {
        switch (role) {
            case 'dispatch': return 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300';
            case 'cell': return 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300';
            default: return 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300';
        }
    };

    return (
        <>
            {/* Indicator pill */}
            <button
                onClick={() => setIsModalOpen(true)}
                className="flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium
                    bg-indigo-50 dark:bg-indigo-900/20 hover:bg-indigo-100 dark:hover:bg-indigo-900/40
                    text-indigo-600 dark:text-indigo-400 transition-colors cursor-pointer select-none"
                title="Workspace Group"
            >
                <span>👥</span>
                <span>Group</span>
                {workspaceRole && (
                    <span className="text-[10px] opacity-70">({workspaceRole})</span>
                )}
            </button>

            {/* Modal overlay */}
            {isModalOpen && (
                <div
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
                    onClick={() => setIsModalOpen(false)}
                >
                    <div
                        className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl border
                            border-gray-200 dark:border-gray-700 w-full max-w-md mx-4 p-6
                            animate-in fade-in zoom-in-95 duration-200"
                        onClick={(e) => e.stopPropagation()}
                    >
                        {/* Header */}
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                                <span>👥</span>
                                {groupData?.display_name || 'Workspace Group'}
                            </h3>
                            <button
                                onClick={() => setIsModalOpen(false)}
                                className="p-1 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                            >
                                <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                </svg>
                            </button>
                        </div>

                        {/* Content */}
                        <div className="space-y-3">
                            {loading && (
                                <div className="text-center py-4 text-gray-400 text-sm">
                                    Loading...
                                </div>
                            )}

                            {error && (
                                <>
                                    <div className="text-center py-2 text-amber-500 text-sm">
                                        {error}
                                    </div>
                                    {/* Fallback: show raw group_id */}
                                    <div className="flex items-center gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                                        <div className="text-sm">
                                            <div className="text-gray-500 dark:text-gray-400 text-xs mb-1">Group ID</div>
                                            <code className="text-xs font-mono text-gray-700 dark:text-gray-300 break-all">
                                                {groupId}
                                            </code>
                                        </div>
                                    </div>
                                    {workspaceRole && (
                                        <div className="flex items-center gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                                            <div className="text-sm">
                                                <div className="text-gray-500 dark:text-gray-400 text-xs mb-1">Role</div>
                                                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${roleColor(workspaceRole)}`}>
                                                    {roleIcon(workspaceRole)} {workspaceRole}
                                                </span>
                                            </div>
                                        </div>
                                    )}
                                </>
                            )}

                            {!loading && !error && groupData && (
                                <>
                                    {/* Member list */}
                                    <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                                        {groupData.members.length} workspace(s)
                                    </div>
                                    <div className="space-y-2 max-h-64 overflow-y-auto">
                                        {groupData.members.map((member) => (
                                            <div
                                                key={member.workspace_id}
                                                className="flex items-center gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50"
                                            >
                                                <span className="text-lg flex-shrink-0">{roleIcon(member.role)}</span>
                                                <div className="flex-1 min-w-0">
                                                    <div className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                                                        {member.title || member.workspace_id}
                                                    </div>
                                                    <div className="flex items-center gap-2 mt-0.5">
                                                        <span className={`inline-flex items-center px-1.5 py-0 rounded text-[10px] font-medium ${roleColor(member.role)}`}>
                                                            {member.role}
                                                        </span>
                                                        {member.visibility && (
                                                            <span className="text-[10px] text-gray-400">
                                                                {member.visibility}
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>

                                    {groupData.members.length === 0 && (
                                        <div className="text-center py-4 text-gray-400 text-sm">
                                            No members
                                        </div>
                                    )}
                                </>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}
