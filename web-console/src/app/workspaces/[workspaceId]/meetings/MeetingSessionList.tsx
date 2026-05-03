'use client';

import type { MeetingSession } from './meetingRecords.types';
import { MeetingSessionCard } from './MeetingSessionCard';

interface MeetingSessionListProps {
    sessions: MeetingSession[];
    selectedSessionId?: string;
    onSelectSession: (session: MeetingSession) => void;
}

export function MeetingSessionList({
    sessions,
    selectedSessionId,
    onSelectSession,
}: MeetingSessionListProps) {
    if (sessions.length === 0) {
        return (
            <div className="text-center py-16">
                <div className="text-lg font-medium text-primary dark:text-gray-300 mb-1">
                    No meeting records yet
                </div>
                <div className="text-sm text-secondary dark:text-gray-400">
                    Persistent Meeting history will appear here once it is enabled for this workspace.
                </div>
            </div>
        );
    }

    return (
        <div className="relative">
            <div className="absolute left-[23px] top-0 bottom-0 w-0.5 bg-default dark:bg-gray-700" />
            <div className="space-y-3">
                {sessions.map((session) => (
                    <MeetingSessionCard
                        key={session.id}
                        session={session}
                        isSelected={selectedSessionId === session.id}
                        onClick={() => onSelectSession(session)}
                    />
                ))}
            </div>
        </div>
    );
}
