import { registryCompletionRecords, summary } from './meetingWorkbenchTestData';

const jsonHeaders = { 'Content-Type': 'application/json' };

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
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

export function createPlaybooksResponse(): Response {
  return jsonResponse([
    {
      playbook_code: 'visual_audit',
      name: 'Visual Audit',
      description: 'Audit visual references',
      capability_code: 'ig',
      required_tools: ['canva'],
    },
    {
      playbook_code: 'generate_reels_asset',
      name: 'Generate Reels Asset',
      description: 'Generate performance direction reels assets',
      capability_code: 'performance_direction',
      required_tools: ['comfyui'],
    },
  ]);
}

export function createObjectCompletionResponse(query: string): Response {
  const results = registryCompletionRecords.filter((record) => {
    const haystack = `${record.token} ${record.label} ${record.description} ${record.owner_pack} ${record.object_kind}`.toLowerCase();
    return !query || haystack.includes(query);
  });
  return jsonResponse({
    workspace_id: 'ws-global',
    query,
    results,
  });
}

export function createObjectActionPlanResponse(): Response {
  return jsonResponse({
    workspace_id: 'ws-global',
    status: 'planned',
    selected_affordance: {
      verb: 'generate_reels_asset',
      label: 'Generate reels asset',
      object_kinds: ['storyboard_scene'],
      input_schema: { type: 'object' },
      output_schema: { type: 'object' },
      required_roles: ['source', 'target', 'character'],
      write_modes: ['staged'],
      planner_backend: 'capabilities.performance_direction.services.aol:plan_reels_asset',
      executor_backend: 'capabilities.performance_direction.services.aol:execute_reels_asset',
    },
    missing_roles: [],
    request_plan: {
      steps: ['load_source_reference', 'patch_storyboard_scene'],
    },
    errors: [],
  });
}

export function createCompositionGraphContractsResponse(): Response {
  return jsonResponse({
    workspace_id: 'ws-global',
    contracts: [
      {
        capability_code: 'performance_direction',
        label: 'Performance Direction',
        enabled: true,
        contract_version: 'composition_graph.v1',
        accepted_object_roles: ['source', 'target'],
        node_types: [
          {
            id: 'director_focus',
            label: 'Director Focus',
            source: 'pack',
            capability_code: 'performance_direction',
            category: 'intent',
            input_ports: [
              { id: 'object', direction: 'input', data_type: 'object_ref', required: false },
            ],
            output_ports: [
              { id: 'focus', direction: 'output', data_type: 'director_focus' },
            ],
            payload_schema: {
              type: 'object',
              required: ['focus'],
              properties: { focus: { type: 'string' } },
            },
          },
          {
            id: 'decision_point',
            label: 'Decision Point',
            source: 'pack',
            capability_code: 'performance_direction',
            input_ports: [
              { id: 'focus', direction: 'input', data_type: 'director_focus', required: true },
            ],
            output_ports: [
              { id: 'decision', direction: 'output', data_type: 'director_decision' },
            ],
            payload_schema: {
              type: 'object',
              required: ['decision'],
              properties: { decision: { type: 'string' } },
            },
          },
          {
            id: 'acceptance_gate',
            label: 'Acceptance Gate',
            source: 'pack',
            capability_code: 'performance_direction',
            input_ports: [
              { id: 'decision', direction: 'input', data_type: 'director_decision', required: true },
            ],
            output_ports: [],
            payload_schema: {
              type: 'object',
              required: ['gate'],
              properties: { gate: { type: 'string' } },
            },
          },
        ],
        edge_types: [{ id: 'contract_edge', label: 'Contract Edge' }],
        compile: {
          backend: 'capabilities.performance_direction.services.director_graph_compile:compile_composition_graph',
          output_mode: 'meeting_command_envelope',
        },
      },
    ],
    diagnostics: [],
  });
}

export function createCompositionGraphDraftResponse(init?: RequestInit): Response {
  const requestBody = readRequestBody(init);
  return jsonResponse({
    workspace_id: 'ws-global',
    draft: {
      id: 'cg_draft_frontend',
      graph_id: 'cg_frontend',
      workspace_id: 'ws-global',
      title: requestBody.title || 'Composition Graph',
      schema_version: 'composition_graph.v1',
      meeting_id: requestBody.meeting_id || 'mtg_global',
      thread_id: requestBody.thread_id || 'mtg_global',
      selected_primary_pack: requestBody.selected_primary_pack,
      nodes: requestBody.nodes || [],
      edges: requestBody.edges || [],
      viewport: requestBody.viewport || { x: 0, y: 0, zoom: 1 },
      metadata: requestBody.metadata || {},
    },
  });
}

export function createCompositionGraphImportResponse(): Response {
  return jsonResponse({
    workspace_id: 'ws-global',
    valid: true,
    diagnostics: [],
  });
}

export function createCompositionGraphNodeOptionsResponse(): Response {
  return jsonResponse({
    workspace_id: 'ws-global',
    node_type: 'comfyui_lane_adapter',
    field: 'workflow_ref',
    options: [],
    diagnostics: [],
    metadata: {},
  });
}

export function createCompositionGraphRunResponse(init?: RequestInit): Response {
  const requestBody = readRequestBody(init);
  return jsonResponse({
    workspace_id: 'ws-global',
    run: {
      id: 'cg_run_frontend',
      graph_id: requestBody.graph_id || 'cg_frontend',
      workspace_id: 'ws-global',
      status: 'succeeded',
      schema_version: 'composition_graph_run.v1',
      draft_id: requestBody.draft_id || null,
      meeting_id: requestBody.meeting_id || 'mtg_global',
      thread_id: requestBody.thread_id || 'mtg_global',
      command: requestBody.command || 'Run graph.',
      nodes: requestBody.nodes || [],
      edges: requestBody.edges || [],
      node_states: Object.fromEntries((requestBody.nodes || []).map((node: { id: string; type: string }) => [
        node.id,
        {
          node_id: node.id,
          node_type: node.type,
          status: 'succeeded',
          outputs: {},
          diagnostics: [],
          metadata: {},
        },
      ])),
      diagnostics: [],
      outputs: {},
      created_at: '2026-05-16T00:00:00Z',
      updated_at: '2026-05-16T00:00:00Z',
      started_at: '2026-05-16T00:00:00Z',
      completed_at: '2026-05-16T00:00:01Z',
      metadata: {},
    },
  });
}

export function createCompositionGraphCompileResponse(init?: RequestInit): Response {
  const requestBody = readRequestBody(init);
  return jsonResponse({
    workspace_id: 'ws-global',
    status: 'succeeded',
    output_mode: 'meeting_command_envelope',
    diagnostics: [],
    command_envelope: {
      meeting_id: requestBody.meeting_id || 'mtg_global',
      thread_id: requestBody.thread_id || 'mtg_global',
      intent_text: requestBody.command || 'Compile the composition graph.',
      meeting_mentions: [],
      context_objects: [],
      requested_action: {
        verb: 'compile_director_guidance',
        pack_code: requestBody.selected_primary_pack || 'performance_direction',
        parameters: {
          source_composition_graph_ref: { graph_id: requestBody.graph_id || 'cg_frontend' },
        },
      },
      metadata: {
        selected_primary_pack: requestBody.selected_primary_pack || 'performance_direction',
        composition_graph_ref: { graph_id: requestBody.graph_id || 'cg_frontend' },
      },
    },
  });
}

export function createObjectActionInvokeResponse(): Response {
  return jsonResponse({
    workspace_id: 'ws-global',
    status: 'succeeded',
    action_plan_id: 'oap_frontend_test',
    execution_id: 'exec-invoked',
    task_id: 'exec-invoked',
    closure: {
      status: 'succeeded',
      output_refs: [
        {
          uri: 'mindscape://performance_direction/generated_reels_asset/exec-invoked',
          owner_pack: 'performance_direction',
          object_kind: 'generated_reels_asset',
          object_id: 'exec-invoked',
        },
      ],
    },
    executor_result: {
      status: 'completed',
    },
    errors: [],
  });
}

export function createMeetingSessionsResponse(): Response {
  return jsonResponse({
    sessions: [
      {
        id: 'mtg_global',
        workspace_id: 'ws-global',
        started_at: '2026-04-27T01:00:00Z',
        is_active: true,
        status: 'active',
        meeting_type: 'direction',
        agenda: ['Global Reference'],
        metadata: {
          addressable_object_layer: {
            status: 'attached',
            context_entries: [
              {
                role: 'source',
                ref: summary.ref,
              },
            ],
            context_attachments: [
              {
                role: 'source',
                object_ref: summary.ref,
                object_summary: {
                  title: summary.title,
                  summary_text: summary.summary_text,
                  labels: summary.labels,
                  owner_surface_url: summary.owner_surface_url,
                },
              },
            ],
            staged_refs: [],
            review_routes: [],
          },
        },
      },
      {
        id: 'mtg_other',
        workspace_id: 'ws-global',
        started_at: '2026-04-27T02:00:00Z',
        is_active: true,
        status: 'active',
        meeting_type: 'direction',
        agenda: ['Other Reference'],
        metadata: {},
      },
    ],
  });
}

export function createMeetingSessionEventsResponse(): Response {
  return jsonResponse({
    events: [
      {
        id: 'event_user',
        timestamp: '2026-04-27T01:01:00Z',
        actor: 'user',
        event_type: 'message',
        payload: {
          message: 'Create a 90 second reels script from this reference',
        },
        metadata: {},
      },
      {
        id: 'event_stage',
        timestamp: '2026-04-27T01:01:05Z',
        actor: 'assistant',
        event_type: 'pipeline_stage',
        payload: {
          stage: 'context_building',
          message: 'Preparing context',
          status: 'running',
        },
        metadata: {},
      },
      {
        id: 'event_result',
        timestamp: '2026-04-27T01:01:20Z',
        actor: 'assistant',
        event_type: 'message',
        payload: {
          message: '0-10: opening shot\\n10-20: visual beat',
        },
        metadata: {},
      },
      ...Array.from({ length: 20 }, (_, index) => ({
        id: `event_action_${index + 1}`,
        timestamp: `2026-04-27T01:02:${String(index).padStart(2, '0')}Z`,
        actor: 'system',
        event_type: 'action_item',
        payload: {
          title: `Governance action item ${index + 1}`,
        },
        metadata: {},
      })),
    ],
  });
}

export function createArtifactsResponse(): Response {
  return jsonResponse({
    artifacts: [
      {
        id: 'artifact_result',
        workspace_id: 'ws-global',
        thread_id: 'mtg_global',
        execution_id: 'exec_result',
        playbook_code: 'external_agent',
        artifact_type: 'data',
        title: 'Task Result: exec_result',
        summary: 'Landed result artifact',
        content: {},
        metadata: {
          source: 'task_runner',
          landing: {
            artifact_dir: '/tmp/artifacts/exec_result',
          },
        },
        created_at: '2026-04-27T01:01:30Z',
      },
    ],
  });
}

export function createEmptyArtifactsResponse(): Response {
  return jsonResponse({ artifacts: [] });
}

export function createEmptyEventsResponse(): Response {
  return jsonResponse({ events: [] });
}

export function createEmptyMeetingSessionEventsResponse(): Response {
  return jsonResponse({ events: [] });
}

export function createAgentsResponse(): Response {
  return jsonResponse({ agents: [] });
}

export function createModelRouteRegistryResponse(): Response {
  return jsonResponse({
    primary_executor_runtime: null,
    surfaces: {},
    dispatch_chain: [],
  });
}

export function createDefaultAcceptedTaskResponse(): Response {
  return jsonResponse({ task_id: 'task-accepted' }, 202);
}
