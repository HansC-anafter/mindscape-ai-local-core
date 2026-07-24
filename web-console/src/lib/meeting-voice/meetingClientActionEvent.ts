import {
  subscribeEventStream,
  type UnifiedEvent,
} from '@/components/workspace/eventProjector';

export const AOL_MEETING_CLIENT_ACTION_EVENT = 'mindscape:aol-meeting-client-action';
export const AOL_MEETING_CLIENT_ACTION_CHANNEL = 'mindscape:aol-meeting-client-actions:v1';

export type AOLMeetingClientAction = {
  schemaVersion: 'aol.client_action.v1';
  actionId: string;
  workspaceId: string;
  meetingId: string;
  packCode: string;
  intentCode: string;
  actionCode: string;
  requiresConfirmation: boolean;
  payload: Record<string, unknown>;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

export function readMeetingClientAction(
  commandResponse: unknown,
): AOLMeetingClientAction | null {
  if (!isRecord(commandResponse)) {
    return null;
  }
  const dispatchResult = isRecord(commandResponse.dispatch_result)
    ? commandResponse.dispatch_result
    : null;
  const clientAction = dispatchResult && isRecord(dispatchResult.client_action)
    ? dispatchResult.client_action
    : null;
  if (!clientAction || clientAction.schema_version !== 'aol.client_action.v1') {
    return null;
  }
  const actionId = readString(commandResponse.command_id);
  const workspaceId = readString(commandResponse.workspace_id);
  const meetingId = readString(commandResponse.meeting_id);
  const packCode = readString(clientAction.pack_code);
  const intentCode = readString(clientAction.intent_code);
  const actionCode = readString(clientAction.action_code);
  const payload = isRecord(clientAction.payload) ? clientAction.payload : null;
  if (!actionId || !workspaceId || !meetingId || !packCode || !intentCode || !actionCode || !payload) {
    return null;
  }
  return {
    schemaVersion: 'aol.client_action.v1',
    actionId,
    workspaceId,
    meetingId,
    packCode,
    intentCode,
    actionCode,
    requiresConfirmation: clientAction.requires_confirmation === true,
    payload,
  };
}

export function dispatchMeetingClientAction(commandResponse: unknown): AOLMeetingClientAction | null {
  const action = readMeetingClientAction(commandResponse);
  if (!action || typeof window === 'undefined') {
    return action;
  }
  window.dispatchEvent(new CustomEvent<AOLMeetingClientAction>(
    AOL_MEETING_CLIENT_ACTION_EVENT,
    { detail: action },
  ));
  if (typeof BroadcastChannel !== 'undefined') {
    const channel = new BroadcastChannel(AOL_MEETING_CLIENT_ACTION_CHANNEL);
    channel.postMessage(action);
    channel.close();
  }
  return action;
}

export function readMeetingClientActionEvent(event: Event): AOLMeetingClientAction | null {
  if (!(event instanceof CustomEvent)) {
    return null;
  }
  const detail = event.detail;
  if (!isRecord(detail)) {
    return null;
  }
  return readMeetingClientAction({
    command_id: detail.actionId,
    workspace_id: detail.workspaceId,
    meeting_id: detail.meetingId,
    dispatch_result: {
      client_action: {
        schema_version: detail.schemaVersion,
        pack_code: detail.packCode,
        intent_code: detail.intentCode,
        action_code: detail.actionCode,
        requires_confirmation: detail.requiresConfirmation,
        payload: detail.payload,
      },
    },
  });
}

export function readMeetingClientActionWorkspaceEvent(
  event: UnifiedEvent,
): AOLMeetingClientAction | null {
  const payload = isRecord(event.payload) ? event.payload : null;
  if (
    event.type !== 'capability_event'
    || !payload
    || payload.event_code !== 'aol_client_action_ready'
    || !isRecord(payload.client_action)
  ) {
    return null;
  }
  return readMeetingClientAction({
    command_id: payload.command_id,
    workspace_id: event.workspace_id,
    meeting_id: payload.meeting_session_id,
    dispatch_result: { client_action: payload.client_action },
  });
}

interface MeetingClientActionSubscriptionOptions {
  workspaceId: string;
  meetingId: string;
  apiUrl?: string;
}

const CLIENT_ACTION_BOOTSTRAP_TIMEOUT_MS = 12_000;

export function readMeetingClientActionCommand(command: unknown): AOLMeetingClientAction | null {
  if (!isRecord(command) || command.status !== 'completed' || !isRecord(command.metadata)) {
    return null;
  }
  const clientAction = isRecord(command.metadata.client_action)
    ? command.metadata.client_action
    : null;
  if (!clientAction || command.metadata.dispatch_status !== 'completed') {
    return null;
  }
  return readMeetingClientAction({
    command_id: command.command_id,
    workspace_id: command.workspace_id,
    meeting_id: command.meeting_id,
    dispatch_result: { client_action: clientAction },
  });
}

async function loadMeetingClientActionCommands(
  options: MeetingClientActionSubscriptionOptions,
  signal: AbortSignal,
): Promise<AOLMeetingClientAction[]> {
  const baseUrl = (options.apiUrl ?? '').trim().replace(/\/+$/, '');
  const response = await fetch(
    `${baseUrl}/api/v1/workspaces/${encodeURIComponent(options.workspaceId)}`
      + `/meetings/${encodeURIComponent(options.meetingId)}/commands?limit=100`,
    {
      credentials: 'same-origin',
      cache: 'no-store',
      signal,
    },
  );
  if (!response.ok) {
    throw new Error(`meeting_client_action_bootstrap_failed_${response.status}`);
  }
  const payload = await response.json() as { commands?: unknown };
  if (!Array.isArray(payload.commands)) {
    throw new Error('meeting_client_action_bootstrap_payload_invalid');
  }
  return payload.commands
    .map(readMeetingClientActionCommand)
    .filter((action): action is AOLMeetingClientAction => action !== null);
}

export function subscribeMeetingClientActions(
  listener: (action: AOLMeetingClientAction) => void,
  options?: MeetingClientActionSubscriptionOptions,
): () => void {
  if (typeof window === 'undefined') {
    return () => undefined;
  }
  const seenActionIds = new Set<string>();
  const bufferedActions: AOLMeetingClientAction[] = [];
  let active = true;
  let bootstrapPending = Boolean(options);
  const deliverNow = (action: AOLMeetingClientAction | null) => {
    if (!action || seenActionIds.has(action.actionId)) {
      return;
    }
    seenActionIds.add(action.actionId);
    if (seenActionIds.size > 64) {
      const oldestActionId = seenActionIds.values().next().value;
      if (typeof oldestActionId === 'string') {
        seenActionIds.delete(oldestActionId);
      }
    }
    listener(action);
  };
  const deliver = (action: AOLMeetingClientAction | null) => {
    if (!action) {
      return;
    }
    if (bootstrapPending) {
      bufferedActions.push(action);
      return;
    }
    deliverNow(action);
  };
  const handleWindowEvent = (event: Event) => {
    deliver(readMeetingClientActionEvent(event));
  };
  const channel = typeof BroadcastChannel !== 'undefined'
    ? new BroadcastChannel(AOL_MEETING_CLIENT_ACTION_CHANNEL)
    : null;
  const handleChannelMessage = (event: MessageEvent<unknown>) => {
    deliver(readMeetingClientAction({
      command_id: isRecord(event.data) ? event.data.actionId : null,
      workspace_id: isRecord(event.data) ? event.data.workspaceId : null,
      meeting_id: isRecord(event.data) ? event.data.meetingId : null,
      dispatch_result: {
        client_action: isRecord(event.data) ? {
          schema_version: event.data.schemaVersion,
          pack_code: event.data.packCode,
          intent_code: event.data.intentCode,
          action_code: event.data.actionCode,
          requires_confirmation: event.data.requiresConfirmation,
          payload: event.data.payload,
        } : null,
      },
    }));
  };
  window.addEventListener(AOL_MEETING_CLIENT_ACTION_EVENT, handleWindowEvent);
  channel?.addEventListener('message', handleChannelMessage);
  const unsubscribeServer = options
    ? subscribeEventStream(options.workspaceId, {
      apiUrl: options.apiUrl,
      eventTypes: ['capability_event'],
      onEvent: (event) => {
        const action = readMeetingClientActionWorkspaceEvent(event);
        if (action?.meetingId === options.meetingId) {
          deliver(action);
        }
      },
    })
    : null;
  const bootstrapController = options ? new AbortController() : null;
  const bootstrapTimeout = options && bootstrapController
    ? window.setTimeout(() => bootstrapController.abort(), CLIENT_ACTION_BOOTSTRAP_TIMEOUT_MS)
    : null;
  if (options && bootstrapController) {
    void loadMeetingClientActionCommands(options, bootstrapController.signal)
      .then((actions) => {
        if (!active) {
          return;
        }
        actions.forEach(deliverNow);
      })
      .catch((error) => {
        if (active && !(error instanceof DOMException && error.name === 'AbortError')) {
          console.warn('[MeetingClientAction] Command ledger bootstrap failed:', error);
        }
      })
      .finally(() => {
        if (bootstrapTimeout !== null) {
          window.clearTimeout(bootstrapTimeout);
        }
        if (!active) {
          return;
        }
        bootstrapPending = false;
        bufferedActions.splice(0).forEach(deliverNow);
      });
  }
  return () => {
    active = false;
    bootstrapController?.abort();
    if (bootstrapTimeout !== null) {
      window.clearTimeout(bootstrapTimeout);
    }
    window.removeEventListener(AOL_MEETING_CLIENT_ACTION_EVENT, handleWindowEvent);
    channel?.removeEventListener('message', handleChannelMessage);
    channel?.close();
    unsubscribeServer?.();
  };
}
