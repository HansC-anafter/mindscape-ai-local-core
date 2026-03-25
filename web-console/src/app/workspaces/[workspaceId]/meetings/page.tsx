'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { formatLocalDateTime } from '@/lib/time';
import { getApiBaseUrl } from '../../../../lib/api-url';
import { GovernedMemoryPreview } from '../../../../components/workspace/governance/GovernedMemoryPreview';
import { WorkflowEvidenceSummary } from '../../../../components/workspace/meeting/WorkflowEvidenceSummary';
import {
    buildPdScenePatchSuccessText,
    buildScenePatchFailureText,
    ScenePatchConsole,
    buildScenePatchSummary,
    parseScenePatchJson,
    scenePatchResultMessage,
} from '../../../../components/workspace/ScenePatchConsole';

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

interface CanonicalMemoryLink {
    memory_item_id: string;
    digest_id?: string;
    writeback_run_id?: string;
    lifecycle_status?: string;
    verification_status?: string;
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
                        {session.status}
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
    autoOpenScenePatch = false,
    onClose,
}: {
    session: MeetingSession;
    workspaceId: string;
    autoOpenScenePatch?: boolean;
    onClose: () => void;
}) {
    const router = useRouter();
    const [showScenePatchPanel, setShowScenePatchPanel] = useState(autoOpenScenePatch);
    const [scenePatchJson, setScenePatchJson] = useState('');
    const [patchSceneId, setPatchSceneId] = useState('');
    const [artifactId, setArtifactId] = useState('');
    const [applyingScenePatch, setApplyingScenePatch] = useState(false);
    const [scenePatchResult, setScenePatchResult] = useState<string | null>(null);
    const actionItems = session.action_items || [];
    const decisions = session.decisions || [];
    const agenda = session.agenda || [];
    const canonicalMemory = session.metadata?.canonical_memory as CanonicalMemoryLink | undefined;
    const workflowEvidenceDiagnostics =
        session.metadata?.workflow_evidence_diagnostics as WorkflowEvidenceDiagnostics | undefined;
    const workflowEvidenceSections = (workflowEvidenceDiagnostics?.section_order || [])
        .map((title) => ({
            title,
            candidateCount: workflowEvidenceDiagnostics?.candidate_counts?.[title] || 0,
            selectedCount: workflowEvidenceDiagnostics?.selected_counts?.[title] || 0,
            droppedCount: workflowEvidenceDiagnostics?.dropped_counts?.[title] || 0,
            limit: workflowEvidenceDiagnostics?.section_limits?.[title] || 0,
        }))
        .filter(
            (section) =>
                section.candidateCount > 0 ||
                section.selectedCount > 0 ||
                section.limit > 0
        );

    const parsedScenePatch = useMemo(
        () => parseScenePatchJson(scenePatchJson),
        [scenePatchJson],
    );

    const scenePatchSummary = useMemo(
        () => buildScenePatchSummary(parsedScenePatch.patch, patchSceneId),
        [parsedScenePatch.patch, patchSceneId],
    );
    const scenePatchResultView = useMemo(
        () => scenePatchResultMessage(scenePatchResult),
        [scenePatchResult],
    );

    useEffect(() => {
        const sourceSceneId = parsedScenePatch.patch?.source_scene_id;
        if (sourceSceneId && !patchSceneId.trim()) {
            setPatchSceneId(sourceSceneId);
        }
    }, [parsedScenePatch.patch?.source_scene_id, patchSceneId]);

    useEffect(() => {
        if (autoOpenScenePatch) {
            setShowScenePatchPanel(true);
        }
    }, [autoOpenScenePatch, session.id]);

    const applyScenePatch = useCallback(async () => {
        if (!parsedScenePatch.patch) {
            setScenePatchResult(parsedScenePatch.error ? `scene patch 解析失敗：${parsedScenePatch.error}` : '請先貼上 storyboard_scene_patch JSON。');
            return;
        }
        if (!patchSceneId.trim()) {
            setScenePatchResult('請填入要套用的 scene_id。');
            return;
        }
        try {
            setApplyingScenePatch(true);
            setScenePatchResult(null);
            const response = await fetch(
                `${API_URL}/api/v1/capabilities/performance_direction/sessions/${encodeURIComponent(session.id)}/storyboard/scene-patch`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        scene_id: patchSceneId.trim(),
                        artifact_id: artifactId.trim() || undefined,
                        storyboard_scene_patch: parsedScenePatch.patch,
                    }),
                }
            );
            if (!response.ok) {
                const detail = await response.text();
                throw new Error(detail || `HTTP ${response.status}`);
            }
            const payload = await response.json();
            setScenePatchResult(
                buildPdScenePatchSuccessText({
                    sceneId: payload.patched_scene_id || patchSceneId.trim(),
                    artifactId: payload.artifact?.artifact_id || null,
                })
            );
        } catch (error) {
            setScenePatchResult(buildScenePatchFailureText('PD', error));
        } finally {
            setApplyingScenePatch(false);
        }
    }, [artifactId, parsedScenePatch.error, parsedScenePatch.patch, patchSceneId, session.id]);

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
                            {session.status}
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

            {canonicalMemory?.memory_item_id && (
                <div className="rounded-lg border border-sky-200 bg-sky-50/70 p-3 dark:border-sky-800 dark:bg-sky-950/30">
                    <label className="text-[10px] font-medium text-sky-700 dark:text-sky-300 uppercase tracking-wide">
                        Governed Memory
                    </label>
                    <div className="mt-1 text-sm text-sky-900 dark:text-sky-100">
                        This meeting already produced a canonical memory item that can be reviewed in the governance workspace.
                    </div>
                    <div className="mt-2 text-xs text-sky-700/90 dark:text-sky-300/90 font-mono break-all">
                        {canonicalMemory.memory_item_id}
                    </div>
                    <button
                        onClick={() => {
                            const params = new URLSearchParams();
                            params.set('tab', 'memory');
                            params.set('memoryId', canonicalMemory.memory_item_id);
                            router.push(`/workspaces/${workspaceId}/governance?${params.toString()}`);
                        }}
                        className="mt-3 w-full rounded-lg bg-sky-600 px-3 py-2 text-sm text-white transition-colors hover:bg-sky-700 dark:bg-sky-700 dark:hover:bg-sky-600"
                    >
                        Open Memory Governance
                    </button>
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
                                    {item.status === 'done' ? 'Done' : 'Open'}
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

            <div className="rounded-lg border border-default dark:border-gray-700 bg-white/70 dark:bg-gray-900/40 p-4 space-y-3">
                <div className="flex items-center justify-between gap-3">
                    <div>
                        <label className="text-[10px] font-medium text-secondary dark:text-gray-400 uppercase tracking-wide">
                            場景 Patch
                        </label>
                        <div className="mt-1 text-sm text-primary dark:text-gray-100">
                            將 LAF / ComfyUI 執行控制台產出的 scene patch 直接套到這筆 PD session。
                        </div>
                    </div>
                    <button
                        onClick={() => setShowScenePatchPanel((current) => !current)}
                        className="rounded-lg border border-default dark:border-gray-600 px-3 py-1.5 text-xs text-secondary dark:text-gray-300 hover:bg-surface-secondary dark:hover:bg-gray-800 transition-colors"
                    >
                        {showScenePatchPanel ? '收合' : '展開'}
                    </button>
                </div>
                {showScenePatchPanel && (
                    <div className="pt-1">
                        <ScenePatchConsole
                            description="將 scene patch 回寫到這筆 PD session 的 storyboard artifact，不在此頁建立新的派送來源。"
                            patchMode="editable"
                            patchJson={scenePatchJson}
                            onPatchJsonChange={setScenePatchJson}
                            patchError={parsedScenePatch.error}
                            summary={scenePatchSummary}
                            sceneId={patchSceneId}
                            onSceneIdChange={setPatchSceneId}
                            onClearPatch={() => {
                                setScenePatchJson('');
                                setPatchSceneId('');
                                setArtifactId('');
                                setScenePatchResult(null);
                            }}
                            pdAction={{
                                sessionId: session.id,
                                onSessionIdChange: () => undefined,
                                sessionIdReadOnly: true,
                                artifactId,
                                onArtifactIdChange: setArtifactId,
                                applying: applyingScenePatch,
                                result: scenePatchResultView,
                                onApply: applyScenePatch,
                                buttonLabel: '套用到此 PD Storyboard',
                                description: '這個入口已綁定當前 Meeting session；僅需確認 scene_id 與可選 artifact_id。',
                            }}
                        />
                    </div>
                )}
            </div>

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
                Open Conversation
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
    const sessionId = searchParams?.get('session_id') || null;
    const openScenePatch = searchParams?.get('open_patch') === '1';

    const [sessions, setSessions] = useState<MeetingSession[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [selectedSession, setSelectedSession] = useState<MeetingSession | null>(null);

    const updateSessionQuery = useCallback(
        (nextSessionId: string | null) => {
            const params = new URLSearchParams(searchParams?.toString() || '');
            if (nextSessionId) {
                params.set('session_id', nextSessionId);
            } else {
                params.delete('session_id');
            }
            const query = params.toString();
            router.replace(
                `/workspaces/${workspaceId}/meetings${query ? `?${query}` : ''}`
            );
        },
        [router, searchParams, workspaceId]
    );

    const handleSelectSession = useCallback(
        async (session: MeetingSession) => {
            try {
                const resp = await fetch(
                    `${API_URL}/api/v1/workspaces/${workspaceId}/meeting-sessions/${session.id}`
                );
                if (resp.ok) {
                    const full = await resp.json();
                    setSelectedSession(full);
                } else {
                    setSelectedSession(session);
                }
            } catch {
                setSelectedSession(session);
            }
            updateSessionQuery(session.id);
        },
        [updateSessionQuery, workspaceId]
    );

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

    useEffect(() => {
        if (!sessionId || loading) {
            return;
        }
        if (selectedSession?.id === sessionId) {
            return;
        }
        const matchedSession = sessions.find((session) => session.id === sessionId);
        if (matchedSession) {
            void handleSelectSession(matchedSession);
        }
    }, [handleSelectSession, loading, selectedSession?.id, sessionId, sessions]);

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
                            <div className="text-lg font-medium text-primary dark:text-gray-300 mb-1">
                                No meeting records yet
                            </div>
                            <div className="text-sm text-secondary dark:text-gray-400">
                                Persistent Meeting history will appear here once it is enabled for this workspace.
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
                            autoOpenScenePatch={openScenePatch}
                            onClose={() => {
                                setSelectedSession(null);
                                updateSessionQuery(null);
                            }}
                        />
                    </div>
                )}
            </div>
        </div>
    );
}
