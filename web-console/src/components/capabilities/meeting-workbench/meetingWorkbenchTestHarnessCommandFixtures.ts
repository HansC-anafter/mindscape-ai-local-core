const jsonHeaders = { 'Content-Type': 'application/json' };

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: jsonHeaders,
  });
}

function readRequestBody(init?: RequestInit): Record<string, any> {
  try {
    return JSON.parse(String(init?.body || '{}'));
  } catch {
    return {};
  }
}

export function createMeetingCommandResponse(init?: RequestInit): Response {
  const requestBody = readRequestBody(init);
  const omitDispatchResult = requestBody?.intent_text === 'No dispatch result fixture';
  const routeObjectAction = requestBody?.metadata?.dispatch_mode === 'route_object_action';
  const routePlaybook = requestBody?.metadata?.dispatch_mode === 'route_playbook';
  const routeMeetingOrchestration = requestBody?.metadata?.dispatch_mode === 'route_meeting_orchestration';
  const routeChat = requestBody?.metadata?.dispatch_mode === 'route_chat';
  const acceptedTaskId = routeObjectAction
    ? 'exec-invoked'
    : routePlaybook
      ? 'exec-playbook'
      : routeMeetingOrchestration
        ? 'task-meeting'
        : routeChat
          ? 'cmd-ledger-global'
          : undefined;
  return jsonResponse({
    workspace_id: 'ws-global',
    meeting_id: 'mtg_global',
    command_id: 'cmd-ledger-global',
    status: routeObjectAction || routeMeetingOrchestration ? 'completed' : 'accepted',
    command: {
      command_id: 'cmd-ledger-global',
      workspace_id: 'ws-global',
      meeting_id: 'mtg_global',
      thread_id: 'mtg_global',
      origin_surface: 'ig.references_grid',
      actor: 'user',
      intent_text: 'Fixture command',
      context_objects: [],
      expected_outputs: [],
      write_mode: 'recommendation_only',
      status: routeObjectAction || routeMeetingOrchestration ? 'completed' : 'accepted',
      accepted_task_id: acceptedTaskId,
      metadata: {},
      created_at: '2026-04-27T01:01:00Z',
      updated_at: '2026-04-27T01:01:00Z',
    },
    dispatch_result: buildDispatchResult({
      omitDispatchResult,
      routeObjectAction,
      routePlaybook,
      routeMeetingOrchestration,
      routeChat,
      requestBody,
    }),
  });
}

function buildDispatchResult({
  omitDispatchResult,
  routeObjectAction,
  routePlaybook,
  routeMeetingOrchestration,
  routeChat,
  requestBody,
}: {
  omitDispatchResult: boolean;
  routeObjectAction: boolean;
  routePlaybook: boolean;
  routeMeetingOrchestration: boolean;
  routeChat: boolean;
  requestBody: Record<string, any>;
}) {
  if (omitDispatchResult) {
    return null;
  }
  if (routeObjectAction) {
    return {
      object_action: {
        status: 'succeeded',
        execution_id: 'exec-invoked',
        task_id: 'exec-invoked',
      },
    };
  }
  if (routePlaybook) {
    return {
      playbook: {
        status: 'accepted',
        task_id: 'exec-playbook',
        triggered_playbook: {
          playbook_code: requestBody?.requested_action?.playbook_code,
          execution_id: 'exec-playbook',
          status: 'triggered',
        },
      },
    };
  }
  if (routeMeetingOrchestration) {
    return {
      meeting_orchestration: {
        status: 'completed',
        task_ir_id: 'task-meeting',
        artifact_landing_status: 'pending',
        request_contract_aol_metadata: {
          selected_guidance_ids: requestBody?.metadata?.selected_guidance_ids || [],
          candidate_playbooks: requestBody?.requested_action?.playbook_code
            ? [
              {
                source: 'selected_pack_tool',
                pack_code: requestBody?.requested_action?.pack_code,
                playbook_code: requestBody?.requested_action?.playbook_code,
              },
            ]
            : [],
        },
      },
    };
  }
  if (routeChat) {
    return {
      chat: {
        status: 'accepted',
        task_id: 'cmd-ledger-global',
        event_id: 'cmd-ledger-global',
        thread_id: 'mtg_global',
      },
    };
  }
  return null;
}
