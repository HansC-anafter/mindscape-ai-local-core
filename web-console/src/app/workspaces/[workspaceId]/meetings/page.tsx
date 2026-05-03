'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { MeetingRecordsHeader } from './MeetingRecordsHeader';
import { MeetingSessionDetailPanel } from './MeetingSessionDetailPanel';
import { MeetingSessionList } from './MeetingSessionList';
import {
    fetchMeetingRecordDetail,
    fetchMeetingRecords,
} from './meetingRecordsApi';
import type { MeetingSession } from './meetingRecords.types';

export default function MeetingRecordsPage() {
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
                `/workspaces/${workspaceId}/meetings${query ? `?${query}` : ''}`,
            );
        },
        [router, searchParams, workspaceId],
    );

    const handleSelectSession = useCallback(
        async (session: MeetingSession) => {
            try {
                const fullSession = await fetchMeetingRecordDetail(workspaceId, session.id);
                setSelectedSession(fullSession || session);
            } catch {
                setSelectedSession(session);
            }
            updateSessionQuery(session.id);
        },
        [updateSessionQuery, workspaceId],
    );

    useEffect(() => {
        const load = async () => {
            try {
                setLoading(true);
                setError(null);
                setSessions(await fetchMeetingRecords(workspaceId, projectId));
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
            <MeetingRecordsHeader
                onBack={() => router.push(`/workspaces/${workspaceId}`)}
            />

            <div className="flex-1 overflow-hidden flex">
                <div className="flex-1 overflow-y-auto p-6">
                    <MeetingSessionList
                        sessions={sessions}
                        selectedSessionId={selectedSession?.id}
                        onSelectSession={handleSelectSession}
                    />
                </div>

                {selectedSession && (
                    <div className="w-[400px] border-l dark:border-gray-700 bg-surface-secondary dark:bg-gray-800 overflow-y-auto">
                        <MeetingSessionDetailPanel
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
