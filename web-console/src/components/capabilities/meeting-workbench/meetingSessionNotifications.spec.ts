import { describe, expect, it } from 'vitest';

import {
  MEETING_SESSION_NOTIFICATION_EVENT,
  readMeetingSessionNotificationEvent,
} from './meetingSessionNotifications';

describe('meetingSessionNotifications', () => {
  it('reads valid session notification events', () => {
    const event = new CustomEvent(MEETING_SESSION_NOTIFICATION_EVENT, {
      detail: {
        workspaceId: 'ws-global',
        meetingId: 'mtg_global',
        tone: 'success',
        title: 'Command completed',
        message: 'exec_1',
        commandId: 'cmd_1',
      },
    });

    expect(readMeetingSessionNotificationEvent(event)).toEqual({
      workspaceId: 'ws-global',
      meetingId: 'mtg_global',
      tone: 'success',
      title: 'Command completed',
      message: 'exec_1',
      commandId: 'cmd_1',
    });
  });

  it('rejects incomplete session notification events', () => {
    expect(readMeetingSessionNotificationEvent(new CustomEvent(MEETING_SESSION_NOTIFICATION_EVENT))).toBeNull();
    expect(readMeetingSessionNotificationEvent(new Event('other-event'))).toBeNull();
  });
});
