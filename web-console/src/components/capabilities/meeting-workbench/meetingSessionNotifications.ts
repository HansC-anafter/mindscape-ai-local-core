export const MEETING_SESSION_NOTIFICATION_EVENT = 'meeting-session-notification';

export type MeetingSessionNotificationTone = 'info' | 'success' | 'warning' | 'error';

export interface MeetingSessionNotificationDetail {
  workspaceId: string;
  meetingId: string;
  tone: MeetingSessionNotificationTone;
  title: string;
  message: string;
  commandId?: string;
}

export function dispatchMeetingSessionNotification(detail: MeetingSessionNotificationDetail) {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(new CustomEvent(MEETING_SESSION_NOTIFICATION_EVENT, { detail }));
}

export function readMeetingSessionNotificationEvent(event: Event): MeetingSessionNotificationDetail | null {
  const detail = event instanceof CustomEvent ? event.detail : null;
  if (!detail || typeof detail !== 'object') {
    return null;
  }
  const candidate = detail as Partial<MeetingSessionNotificationDetail>;
  if (!candidate.workspaceId || !candidate.meetingId || !candidate.title || !candidate.message) {
    return null;
  }
  return {
    workspaceId: candidate.workspaceId,
    meetingId: candidate.meetingId,
    tone: candidate.tone || 'info',
    title: candidate.title,
    message: candidate.message,
    commandId: candidate.commandId,
  };
}
