import { describe, expect, it } from 'vitest';

import { normalizeWorkspaceEvent } from './eventStream';

describe('normalizeWorkspaceEvent', () => {
  it('unwraps the canonical committed-workspace CloudEvent envelope', () => {
    expect(normalizeWorkspaceEvent({
      specversion: '1.0',
      id: 'evt_action',
      type: 'mindscape.workspace.capability_event.v1',
      time: '2026-07-16T11:40:00Z',
      workspaceid: 'ws_test',
      data: {
        id: 'evt_action',
        event_type: 'capability_event',
        timestamp: '2026-07-16T11:40:00Z',
        actor: 'system',
        workspace_id: 'ws_test',
        profile_id: 'profile_test',
        thread_id: 'mtg_test',
        payload: {
          event_code: 'aol_client_action_ready',
          meeting_session_id: 'mtg_test',
          command_id: 'cmd_test',
        },
        metadata: { meeting_session_id: 'mtg_test' },
      },
    })).toMatchObject({
      id: 'evt_action',
      type: 'capability_event',
      workspace_id: 'ws_test',
      thread_id: 'mtg_test',
      payload: {
        event_code: 'aol_client_action_ready',
        command_id: 'cmd_test',
      },
    });
  });

  it('preserves the legacy flat workspace event shape', () => {
    expect(normalizeWorkspaceEvent({
      id: 'evt_legacy',
      type: 'meeting_stage',
      timestamp: '2026-07-16T11:40:00Z',
      actor: 'system',
      workspace_id: 'ws_test',
      profile_id: 'profile_test',
      payload: { meeting_session_id: 'mtg_test' },
    })).toMatchObject({
      id: 'evt_legacy',
      type: 'meeting_stage',
      workspace_id: 'ws_test',
    });
  });
});
