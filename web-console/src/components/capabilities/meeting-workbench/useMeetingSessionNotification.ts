import { useEffect, useState } from 'react';

import {
  MEETING_SESSION_NOTIFICATION_EVENT,
  readMeetingSessionNotificationEvent,
  type MeetingSessionNotificationDetail,
} from './meetingSessionNotifications';

export function useMeetingSessionNotification({
  workspaceId,
  activeMeetingId,
}: {
  workspaceId: string;
  activeMeetingId: string | null;
}) {
  const [sessionNotification, setSessionNotification] = useState<MeetingSessionNotificationDetail | null>(null);

  useEffect(() => {
    setSessionNotification(null);
  }, [activeMeetingId]);

  useEffect(() => {
    function handleSessionNotification(event: Event) {
      const notification = readMeetingSessionNotificationEvent(event);
      if (!notification || notification.workspaceId !== workspaceId || notification.meetingId !== activeMeetingId) {
        return;
      }
      setSessionNotification(notification);
    }

    window.addEventListener(MEETING_SESSION_NOTIFICATION_EVENT, handleSessionNotification);
    return () => {
      window.removeEventListener(MEETING_SESSION_NOTIFICATION_EVENT, handleSessionNotification);
    };
  }, [activeMeetingId, workspaceId]);

  return {
    sessionNotification,
    clearSessionNotification: () => setSessionNotification(null),
  };
}
