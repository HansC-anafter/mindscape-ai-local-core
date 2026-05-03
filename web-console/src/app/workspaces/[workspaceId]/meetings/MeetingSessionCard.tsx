'use client';

import { formatLocalDateTime } from '@/lib/time';
import type { MeetingSession, WorkflowEvidenceDiagnostics } from './meetingRecords.types';
import { getMeetingRecordStatusStyle } from './meetingRecordsUtils';

interface MeetingSessionCardProps {
    session: MeetingSession;
    isSelected: boolean;
    onClick: () => void;
}

export function MeetingSessionCard({ session, isSelected, onClick }: MeetingSessionCardProps) {
    const actionItemCount = session.action_items?.length || 0;
    const workflowEvidenceDiagnostics =
        session.metadata?.workflow_evidence_diagnostics as WorkflowEvidenceDiagnostics | undefined;

    return (
        <div
            className={`relative flex items-start gap-4 cursor-pointer p-4 rounded-lg transition-colors ${isSelected
                    ? 'bg-sky-50 dark:bg-sky-900/20 ring-1 ring-sky-300 dark:ring-sky-700'
                    : 'hover:bg-surface-secondary dark:hover:bg-gray-800'
                }`}
            onClick={onClick}
        >
            <div
                className={`relative z-10 w-4 h-4 rounded-full border-2 flex-shrink-0 mt-1 ${session.is_active
                        ? 'bg-green-500 border-green-300 dark:border-green-700'
                        : 'bg-gray-400 border-gray-300 dark:bg-gray-500 dark:border-gray-600'
                    }`}
            />
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${getMeetingRecordStatusStyle(session.status)}`}>
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

                {workflowEvidenceDiagnostics && (
                    <div className="mb-1 text-xs text-secondary dark:text-gray-400">
                        workflow packet · {workflowEvidenceDiagnostics.profile || 'general'} · {workflowEvidenceDiagnostics.scope || 'none'} · {workflowEvidenceDiagnostics.selected_line_count || 0}/{workflowEvidenceDiagnostics.total_line_budget || 0} lines
                    </div>
                )}

                <div className="text-xs text-secondary dark:text-gray-500">
                    {formatLocalDateTime(session.started_at)}
                    {session.ended_at && (
                        <span className="ml-2">
                            → {formatLocalDateTime(session.ended_at)}
                        </span>
                    )}
                </div>

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
