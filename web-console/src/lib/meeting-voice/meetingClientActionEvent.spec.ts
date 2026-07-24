import { describe, expect, it, vi } from 'vitest';

const { subscribeEventStreamMock } = vi.hoisted(() => ({
  subscribeEventStreamMock: vi.fn((
    _workspaceId: string,
    _options: {
      apiUrl?: string;
      eventTypes?: string[];
      onEvent: (event: unknown) => void;
    },
  ) => vi.fn()),
}));

vi.mock('@/components/workspace/eventProjector', () => ({
  subscribeEventStream: subscribeEventStreamMock,
}));

import {
  AOL_MEETING_CLIENT_ACTION_CHANNEL,
  AOL_MEETING_CLIENT_ACTION_EVENT,
  dispatchMeetingClientAction,
  readMeetingClientAction,
  readMeetingClientActionCommand,
  readMeetingClientActionWorkspaceEvent,
  subscribeMeetingClientActions,
} from './meetingClientActionEvent';

const response = {
  workspace_id: 'ws_test',
  meeting_id: 'mtg_test',
  command_id: 'cmd_test',
  dispatch_result: {
    client_action: {
      schema_version: 'aol.client_action.v1',
      pack_code: 'yogacoach',
      intent_code: 'prepare_default_reference_practice',
      action_code: 'yogacoach.prepare_reference_practice',
      requires_confirmation: true,
      payload: {
        playback: { duration_ms: 1_800_000 },
      },
    },
  },
};

describe('meetingClientActionEvent', () => {
  it('reads the bounded client action from a Meeting ledger response', () => {
    expect(readMeetingClientAction(response)).toEqual({
      schemaVersion: 'aol.client_action.v1',
      actionId: 'cmd_test',
      workspaceId: 'ws_test',
      meetingId: 'mtg_test',
      packCode: 'yogacoach',
      intentCode: 'prepare_default_reference_practice',
      actionCode: 'yogacoach.prepare_reference_practice',
      requiresConfirmation: true,
      payload: {
        playback: { duration_ms: 1_800_000 },
      },
    });
  });

  it('dispatches one browser event without polling', () => {
    const listener = vi.fn();
    window.addEventListener(AOL_MEETING_CLIENT_ACTION_EVENT, listener);
    dispatchMeetingClientAction(response);
    window.removeEventListener(AOL_MEETING_CLIENT_ACTION_EVENT, listener);

    expect(listener).toHaveBeenCalledTimes(1);
    expect((listener.mock.calls[0][0] as CustomEvent).detail.actionCode).toBe(
      'yogacoach.prepare_reference_practice',
    );
  });

  it('broadcasts the canonical action to another same-origin workbench tab', () => {
    const postMessage = vi.fn();
    const close = vi.fn();
    vi.stubGlobal('BroadcastChannel', class {
      name: string;

      constructor(name: string) {
        this.name = name;
      }

      postMessage = postMessage;
      close = close;
    });

    dispatchMeetingClientAction(response);

    expect(postMessage).toHaveBeenCalledWith(expect.objectContaining({
      actionId: 'cmd_test',
      actionCode: 'yogacoach.prepare_reference_practice',
    }));
    expect(close).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });

  it('subscribes to both same-tab and cross-tab delivery while deduplicating action ids', () => {
    let messageListener: (event: MessageEvent<unknown>) => void = () => undefined;
    const removeEventListener = vi.fn();
    const close = vi.fn();
    vi.stubGlobal('BroadcastChannel', class {
      name: string;

      constructor(name: string) {
        this.name = name;
      }

      addEventListener(_type: string, listener: (event: MessageEvent<unknown>) => void) {
        messageListener = listener;
      }

      removeEventListener = removeEventListener;
      postMessage() {}
      close = close;
    });
    const listener = vi.fn();
    const unsubscribe = subscribeMeetingClientActions(listener);
    const action = readMeetingClientAction(response);
    expect(action).not.toBeNull();

    window.dispatchEvent(new CustomEvent(AOL_MEETING_CLIENT_ACTION_EVENT, { detail: action }));
    messageListener(new MessageEvent('message', { data: action }));

    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenCalledWith(expect.objectContaining({ actionId: 'cmd_test' }));
    unsubscribe();
    expect(removeEventListener).toHaveBeenCalledTimes(1);
    expect(close).toHaveBeenCalledTimes(1);
    expect(AOL_MEETING_CLIENT_ACTION_CHANNEL).toContain('aol-meeting-client-actions');
    vi.unstubAllGlobals();
  });

  it('rejects non-canonical or incomplete action payloads', () => {
    expect(readMeetingClientAction({
      ...response,
      dispatch_result: {
        client_action: {
          ...response.dispatch_result.client_action,
          schema_version: 'unknown.v1',
        },
      },
    })).toBeNull();
  });

  it('reads only completed client actions from the durable command ledger', () => {
    const command = {
      command_id: 'cmd_test',
      workspace_id: 'ws_test',
      meeting_id: 'mtg_test',
      status: 'completed',
      metadata: {
        dispatch_status: 'completed',
        client_action: response.dispatch_result.client_action,
      },
    };

    expect(readMeetingClientActionCommand(command)).toEqual(expect.objectContaining({
      actionId: 'cmd_test',
      actionCode: 'yogacoach.prepare_reference_practice',
    }));
    expect(readMeetingClientActionCommand({
      ...command,
      metadata: { ...command.metadata, dispatch_status: 'failed' },
    })).toBeNull();
  });

  it('delivers a meeting-scoped client action from the canonical workspace SSE stream', async () => {
    subscribeEventStreamMock.mockClear();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ commands: [] }),
    }));
    const listener = vi.fn();
    const unsubscribe = subscribeMeetingClientActions(listener, {
      workspaceId: 'ws_test',
      meetingId: 'mtg_test',
      apiUrl: 'http://api.test',
    });
    expect(subscribeEventStreamMock).toHaveBeenCalledWith('ws_test', expect.objectContaining({
      apiUrl: 'http://api.test',
      eventTypes: ['capability_event'],
    }));

    const streamOptions = subscribeEventStreamMock.mock.calls[0][1];
    streamOptions.onEvent({
      id: 'evt_test',
      type: 'capability_event',
      timestamp: '2026-07-16T11:40:00Z',
      actor: 'system',
      workspace_id: 'ws_test',
      profile_id: 'profile_test',
      thread_id: 'mtg_test',
      payload: {
        event_code: 'aol_client_action_ready',
        meeting_session_id: 'mtg_test',
        command_id: 'cmd_test',
        client_action: response.dispatch_result.client_action,
      },
    });

    await vi.waitFor(() => expect(listener).toHaveBeenCalledTimes(1));
    expect(listener).toHaveBeenCalledWith(expect.objectContaining({
      actionId: 'cmd_test',
      meetingId: 'mtg_test',
      actionCode: 'yogacoach.prepare_reference_practice',
    }));
    unsubscribe();
    vi.unstubAllGlobals();
  });

  it('replays ledger actions before buffered SSE actions and deduplicates by action id', async () => {
    subscribeEventStreamMock.mockClear();
    let resolveLedger: (value: unknown) => void = () => undefined;
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise((resolve) => {
      resolveLedger = resolve;
    })));
    const listener = vi.fn();
    const unsubscribe = subscribeMeetingClientActions(listener, {
      workspaceId: 'ws_test',
      meetingId: 'mtg_test',
      apiUrl: 'http://api.test',
    });
    const streamOptions = subscribeEventStreamMock.mock.calls[0][1];
    const confirmClientAction = {
      ...response.dispatch_result.client_action,
      intent_code: 'confirm_default_reference_practice',
      action_code: 'yogacoach.confirm_reference_practice',
      requires_confirmation: false,
    };
    streamOptions.onEvent({
      id: 'evt_confirm',
      type: 'capability_event',
      timestamp: '2026-07-16T11:41:00Z',
      actor: 'system',
      workspace_id: 'ws_test',
      profile_id: 'profile_test',
      thread_id: 'mtg_test',
      payload: {
        event_code: 'aol_client_action_ready',
        meeting_session_id: 'mtg_test',
        command_id: 'cmd_confirm',
        client_action: confirmClientAction,
      },
    });
    expect(listener).not.toHaveBeenCalled();

    resolveLedger({
      ok: true,
      json: async () => ({
        commands: [
          {
            command_id: 'cmd_prepare',
            workspace_id: 'ws_test',
            meeting_id: 'mtg_test',
            status: 'completed',
            metadata: {
              dispatch_status: 'completed',
              client_action: response.dispatch_result.client_action,
            },
          },
          {
            command_id: 'cmd_confirm',
            workspace_id: 'ws_test',
            meeting_id: 'mtg_test',
            status: 'completed',
            metadata: {
              dispatch_status: 'completed',
              client_action: confirmClientAction,
            },
          },
        ],
      }),
    });

    await vi.waitFor(() => expect(listener).toHaveBeenCalledTimes(2));
    expect(listener.mock.calls.map(([action]) => action.actionCode)).toEqual([
      'yogacoach.prepare_reference_practice',
      'yogacoach.confirm_reference_practice',
    ]);
    unsubscribe();
    vi.unstubAllGlobals();
  });

  it('rejects workspace capability events that are not AOL client actions', () => {
    expect(readMeetingClientActionWorkspaceEvent({
      id: 'evt_other',
      type: 'capability_event',
      timestamp: '',
      actor: 'system',
      workspace_id: 'ws_test',
      profile_id: 'profile_test',
      payload: { event_code: 'another_capability_event' },
    })).toBeNull();
  });
});
