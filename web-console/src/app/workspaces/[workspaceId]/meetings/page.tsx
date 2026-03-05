'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { formatLocalDateTime } from '@/lib/time';
import { getApiBaseUrl } from '../../../../lib/api-url';

const API_URL = getApiBaseUrl();

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MeetingSession {
    id: string;
    workspace_id: string;
    project_id?: string;
    thread_id?: string;
    started_at: string;
    ended_at?: string | null;
    is_active: boolean;
    status: string;
    meeting_type: string;
    agenda: string[];
    success_criteria: string[];
    round_count: number;
    max_rounds: number;
    action_items: ActionItem[];
    decisions: string[];
    minutes_md: string;
    metadata: Record<string, any>;
}

interface ActionItem {
    description?: string;
    status?: string;
    assignee?: string;
    [key: string]: any;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getStatusStyle(status: string): string {
    const styles: Record<string, string> = {
        active: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300',
        planned: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300',
        closing: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300',
        closed: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
        aborted: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
        failed: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300',
    };
    return styles[status] || 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300';
}

function getStatusIcon(status: string): string {
    const icons: Record<string, string> = {
        active: '🟢',
        planned: '📋',
        closing: '⏳',
        closed: '✅',
        aborted: '🚫',
        failed: '❌',
    };
    return icons[status] || '•';
}

// ---------------------------------------------------------------------------
// Session Card (list item)
// ---------------------------------------------------------------------------

function SessionCard({
    session,
    isSelected,
    onClick,
}: {
    session: MeetingSession;
    isSelected: boolean;
    onClick: () => void;
}) {
    const actionItemCount = session.action_items?.length || 0;

    return (
        <div
            className={`relative flex items-start gap-4 cursor-pointer p-4 rounded-lg transition-colors ${isSelected
                    ? 'bg-sky-50 dark:bg-sky-900/20 ring-1 ring-sky-300 dark:ring-sky-700'
                    : 'hover:bg-surface-secondary dark:hover:bg-gray-800'
                }`}
            onClick={onClick}
        >
            {/* Timeline dot */}
            <div
                className={`relative z-10 w-4 h-4 rounded-full border-2 flex-shrink-0 mt-1 ${session.is_active
                        ? 'bg-green-500 border-green-300 dark:border-green-700'
                        : 'bg-gray-400 border-gray-300 dark:bg-gray-500 dark:border-gray-600'
                    }`}
            />

            {/* Content */}
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${getStatusStyle(session.status)}`}>
                        {getStatusIcon(session.status)} {session.status}
                    </span>
                    <span className="text-xs text-secondary dark:text-gray-400">
                        {session.meeting_type}
                    </span>
                </div>

                <div className="text-sm text-primary dark:text-gray-200 mb-1">
                    Round {session.round_count}/{session.max_rounds}
                    {actionItemCount > 0 && (
                        <span className="ml-2 text-xs text-sky-700 dark:text-sky-400">
                            · {actionItemCount} action items
                        </span>
                    )}
                </div>

                <div className="text-xs text-secondary dark:text-gray-500">
                    {formatLocalDateTime(session.started_at)}
                    {session.ended_at && (
                        <span className="ml-2">
                            → {formatLocalDateTime(session.ended_at)}
                        </span>
                    )}
                </div>

                {/* Minutes preview */}
                {session.minutes_md && (
                    <div className="mt-1.5 text-xs text-tertiary dark:text-gray-500 line-clamp-2 italic">
                        {session.minutes_md.slice(0, 120)}
                        {session.minutes_md.length > 120 && '…'}
                    </div>
                )}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Detail Panel
// ---------------------------------------------------------------------------

function SessionDetail({
    session,
    workspaceId,
    onClose,
}: {
    session: MeetingSession;
    workspaceId: string;
    onClose: () => void;
}) {
    const router = useRouter();
    const actionItems = session.action_items || [];
    const decisions = session.decisions || [];
    const agenda = session.agenda || [];

    return (
        <div className="p-5 space-y-5">
            {/* Header */}
            <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-primary dark:text-gray-100">
                    Session Detail
                </h2>
                <button
                    onClick={onClose}
                    className="text-secondary hover:text-primary dark:hover:text-gray-300 text-lg"
                >
                    ✕
                </button>
            </div>

            {/* Status + Rounds */}
            <div className="grid grid-cols-2 gap-3">
                <div>
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Status
                    </label>
                    <div className="mt-1">
                        <span className={`text-xs px-2 py-1 rounded ${getStatusStyle(session.status)}`}>
                            {getStatusIcon(session.status)} {session.status}
                        </span>
                    </div>
                </div>
                <div>
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Rounds
                    </label>
                    <div className="text-sm text-primary dark:text-gray-100 mt-1">
                        {session.round_count} / {session.max_rounds}
                    </div>
                </div>
                <div>
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Type
                    </label>
                    <div className="text-sm text-primary dark:text-gray-100 mt-1">
                        {session.meeting_type}
                    </div>
                </div>
                <div>
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Started
                    </label>
                    <div className="text-sm text-primary dark:text-gray-100 mt-1">
                        {formatLocalDateTime(session.started_at)}
                    </div>
                </div>
            </div>

            {session.ended_at && (
                <div>
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Ended
                    </label>
                    <div className="text-sm text-primary dark:text-gray-100 mt-1">
                        {formatLocalDateTime(session.ended_at)}
                    </div>
                </div>
            )}

            {/* Agenda */}
            {agenda.length > 0 && (
                <div>
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Agenda
                    </label>
                    <ul className="mt-1 space-y-1">
                        {agenda.map((item, i) => (
                            <li key={i} className="text-sm text-primary dark:text-gray-200 flex items-start gap-2">
                                <span className="text-xs text-tertiary mt-0.5">{i + 1}.</span>
                                <span>{item}</span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Minutes */}
            {session.minutes_md && (
                <div>
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Minutes
                    </label>
                    <div className="mt-1 p-3 bg-surface-secondary dark:bg-gray-800 rounded text-sm text-primary dark:text-gray-200 whitespace-pre-wrap max-h-60 overflow-y-auto leading-relaxed">
                        {session.minutes_md}
                    </div>
                </div>
            )}

            {/* Action Items */}
            {actionItems.length > 0 && (
                <div>
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Action Items ({actionItems.length})
                    </label>
                    <div className="mt-1 space-y-2">
                        {actionItems.map((item, i) => (
                            <div
                                key={i}
                                className="flex items-start gap-2 p-2 bg-surface-secondary dark:bg-gray-800 rounded"
                            >
                                <span className={`text-xs mt-0.5 ${item.status === 'done' ? 'text-green-600' : 'text-secondary'
                                    }`}>
                                    {item.status === 'done' ? '✅' : '☐'}
                                </span>
                                <div className="flex-1 min-w-0">
                                    <div className="text-sm text-primary dark:text-gray-200">
                                        {item.description || JSON.stringify(item)}
                                    </div>
                                    {item.assignee && (
                                        <div className="text-xs text-tertiary dark:text-gray-500 mt-0.5">
                                            → {item.assignee}
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Decisions */}
            {decisions.length > 0 && (
                <div>
                    <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                        Decisions ({decisions.length})
                    </label>
                    <div className="mt-1 space-y-1">
                        {decisions.map((d, i) => (
                            <div key={i} className="text-xs text-primary dark:text-gray-300 p-1.5 bg-surface-secondary dark:bg-gray-800 rounded font-mono truncate">
                                {d}
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Navigate to conversation */}
            <button
                onClick={() => {
                    const params = new URLSearchParams();
                    if (session.project_id) params.set('project_id', session.project_id);
                    params.set('meeting', '1');
                    params.set('meeting_session_id', session.id);
                    router.push(`/workspaces/${workspaceId}?${params.toString()}`);
                }}
                className="w-full px-4 py-2 bg-sky-600 dark:bg-sky-700 text-white text-sm rounded-lg hover:bg-sky-700 dark:hover:bg-sky-600 transition-colors"
            >
                查看對話
            </button>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function MeetingWorkbenchPage() {
    const params = useParams();
    const searchParams = useSearchParams();
    const router = useRouter();
    const workspaceId = params?.workspaceId as string;
    const projectId = searchParams?.get('project_id') || null;

    const [sessions, setSessions] = useState<MeetingSession[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [selectedSession, setSelectedSession] = useState<MeetingSession | null>(null);

    // Load sessions
    useEffect(() => {
        const load = async () => {
            try {
                setLoading(true);
                setError(null);
                const qs = projectId ? `?project_id=${projectId}&limit=50` : '?limit=50';
                const resp = await fetch(
                    `${API_URL}/api/v1/workspaces/${workspaceId}/meeting-sessions${qs}`
                );
                if (!resp.ok) throw new Error(`Failed: ${resp.statusText}`);
                const data = await resp.json();
                setSessions(data.sessions || []);
            } catch (e) {
                setError(e instanceof Error ? e.message : 'Failed to load sessions');
            } finally {
                setLoading(false);
            }
        };
        load();
    }, [workspaceId, projectId]);

    // When a session is selected from the list, fetch full detail
    const handleSelectSession = async (session: MeetingSession) => {
        try {
            const resp = await fetch(
                `${API_URL}/api/v1/workspaces/${workspaceId}/meeting-sessions/${session.id}`
            );
            if (resp.ok) {
                const full = await resp.json();
                setSelectedSession(full);
            } else {
                // Fallback to list data
                setSelectedSession(session);
            }
        } catch {
            setSelectedSession(session);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="text-secondary dark:text-gray-400">Loading meeting sessions…</div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="text-red-500 dark:text-red-400">Error: {error}</div>
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full overflow-hidden">
            {/* Header */}
            <div className="px-6 py-4 border-b dark:border-gray-700 bg-surface-secondary dark:bg-gray-900 flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-primary dark:text-gray-100">
                        Meeting Records
                    </h1>
                    <p className="text-sm text-secondary dark:text-gray-400 mt-1">
                        Session history, decisions, and action items
                    </p>
                </div>
                <button
                    onClick={() => router.push(`/workspaces/${workspaceId}`)}
                    className="px-3 py-1.5 text-sm text-secondary dark:text-gray-400 hover:text-primary dark:hover:text-gray-200 border border-default dark:border-gray-600 rounded-lg hover:bg-surface-secondary dark:hover:bg-gray-800 transition-colors"
                >
                    ← Back
                </button>
            </div>

            {/* Main content */}
            <div className="flex-1 overflow-hidden flex">
                {/* Session list */}
                <div className="flex-1 overflow-y-auto p-6">
                    {sessions.length === 0 ? (
                        <div className="text-center py-16">
                            <div className="text-4xl mb-3">🧭</div>
                            <div className="text-lg font-medium text-primary dark:text-gray-300 mb-1">
                                尚無 Meeting 紀錄
                            </div>
                            <div className="text-sm text-secondary dark:text-gray-400">
                                啟用 Persistent Meeting 後，對話紀錄會顯示在這裡
                            </div>
                        </div>
                    ) : (
                        <div className="relative">
                            {/* Timeline line */}
                            <div className="absolute left-[23px] top-0 bottom-0 w-0.5 bg-default dark:bg-gray-700" />

                            {/* Session items */}
                            <div className="space-y-3">
                                {sessions.map((session) => (
                                    <SessionCard
                                        key={session.id}
                                        session={session}
                                        isSelected={selectedSession?.id === session.id}
                                        onClick={() => handleSelectSession(session)}
                                    />
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                {/* Detail panel */}
                {selectedSession && (
                    <div className="w-[400px] border-l dark:border-gray-700 bg-surface-secondary dark:bg-gray-800 overflow-y-auto">
                        <SessionDetail
                            session={selectedSession}
                            workspaceId={workspaceId}
                            onClose={() => setSelectedSession(null)}
                        />
                    </div>
                )}
            </div>
        </div>
    );
}
