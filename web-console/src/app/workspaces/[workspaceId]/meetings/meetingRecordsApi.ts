import { getApiBaseUrl } from '../../../../lib/api-url';
import type { MeetingSession } from './meetingRecords.types';

export const MEETING_RECORDS_API_URL = getApiBaseUrl();

export async function fetchMeetingRecords(
    workspaceId: string,
    projectId: string | null,
): Promise<MeetingSession[]> {
    const qs = projectId ? `?project_id=${projectId}&limit=50` : '?limit=50';
    const response = await fetch(
        `${MEETING_RECORDS_API_URL}/api/v1/workspaces/${workspaceId}/meeting-sessions${qs}`,
    );
    if (!response.ok) {
        throw new Error(`Failed: ${response.statusText}`);
    }
    const data = await response.json();
    return data.sessions || [];
}

export async function fetchMeetingRecordDetail(
    workspaceId: string,
    sessionId: string,
): Promise<MeetingSession | null> {
    const response = await fetch(
        `${MEETING_RECORDS_API_URL}/api/v1/workspaces/${workspaceId}/meeting-sessions/${sessionId}`,
    );
    if (!response.ok) {
        return null;
    }
    return response.json();
}
