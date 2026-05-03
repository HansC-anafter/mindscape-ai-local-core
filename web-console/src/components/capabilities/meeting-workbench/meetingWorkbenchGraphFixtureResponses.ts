import { performanceDirectionSummary, summary } from './meetingWorkbenchTestData';

const jsonHeaders = { 'Content-Type': 'application/json' };

function readRequestedObjectRefs(init?: RequestInit): Array<Record<string, unknown>> {
  try {
    const body = JSON.parse(String(init?.body || '{}'));
    return Array.isArray(body.objects) ? body.objects.filter((item: unknown) => item && typeof item === 'object') : [];
  } catch {
    return [];
  }
}

function createIgReferenceProjection() {
  return {
    ref: summary.ref,
    summary,
    node_kind: 'reference',
    relations: [
      {
        relation_kind: 'directs',
        direction: 'outbound',
        target_ref: performanceDirectionSummary.ref,
      },
    ],
    guidance: [
      {
        id: 'ig-director-framing',
        title: 'Director framing',
        description: 'Turn the IG reference into the next performance direction beat.',
        intent: 'next_step_guidance',
        command_template: 'Draft a shot plan for @object:ref_global before generating assets.',
        review_label: 'Review shot proposal',
        review_routes: ['/workspaces/ws-global/capabilities/performance_direction/review/proposal_01'],
        proposal_ref: {
          uri: 'mindscape://performance_direction/storyboard_proposal/proposal_01',
          owner_pack: 'performance_direction',
          object_kind: 'storyboard_proposal',
          object_id: 'proposal_01',
          workspace_id: 'ws-global',
        },
        target_ref: performanceDirectionSummary.ref,
        required_roles: ['target'],
        priority: 10,
      },
    ],
    metadata: {
      projection_source: 'ig_pack_graph_projection',
    },
  };
}

function createPerformanceDirectionProjection() {
  return {
    ref: performanceDirectionSummary.ref,
    summary: performanceDirectionSummary,
    node_kind: 'storyboard',
    relations: [
      {
        relation_kind: 'guided_by',
        direction: 'inbound',
        target_ref: summary.ref,
      },
    ],
    guidance: [
      {
        id: 'pd-reels-generation-pass',
        title: 'Reels generation pass',
        description: 'Convert the storyboard into a runtime-ready asset generation pass.',
        intent: 'runtime_dispatch',
        command_template: 'Generate the reels asset pass for @storyboard:pd_session_1.',
        review_label: 'Review generated reels pass',
        review_routes: ['/workspaces/ws-global/capabilities/performance_direction/review/pd_session_1'],
        target_ref: {
          uri: 'mindscape://performance_direction/generated_reels_asset/pd_session_1:latest',
          owner_pack: 'performance_direction',
          object_kind: 'generated_reels_asset',
          object_id: 'pd_session_1:latest',
          workspace_id: 'ws-global',
        },
        required_roles: [],
        priority: 10,
      },
    ],
    metadata: {
      projection_source: 'performance_direction_graph_projection',
    },
  };
}

export function createObjectGraphProjectResponse(init?: RequestInit): Response {
  const requestedRefs = readRequestedObjectRefs(init);
  const hasPerformanceDirectionRef = requestedRefs.some((ref) => ref.owner_pack === 'performance_direction');
  const projections = hasPerformanceDirectionRef
    ? [createPerformanceDirectionProjection()]
    : [createIgReferenceProjection()];

  return new Response(JSON.stringify({
    workspace_id: 'ws-global',
    projections,
    errors: [],
  }), {
    status: 200,
    headers: jsonHeaders,
  });
}

export function createExecutionGraphResponse(): Response {
  return new Response(JSON.stringify({
    workspace_id: 'ws-global',
    meeting_id: 'mtg_global',
    nodes: [
      {
        id: 'command-oap-global',
        eyebrow: 'Command',
        title: 'Produce generic asset',
        detail: 'produce_asset · plan oap-global',
        status: 'accepted',
        kind: 'command',
        lane: 'commands',
        metadata: {
          command_id: 'cmd-ledger-global',
          ledger_status: 'accepted',
          projection_source: 'command_ledger',
        },
      },
      {
        id: 'run-task-global',
        eyebrow: 'Run',
        title: 'fixture_runtime',
        detail: 'succeeded · task task-global',
        status: 'ready',
        kind: 'run',
        lane: 'runs',
      },
      {
        id: 'closure-oap-global',
        eyebrow: 'Closure',
        title: 'Action closed',
        detail: '1 outputs · 2 relations',
        status: 'ready',
        kind: 'result',
        lane: 'outputs',
      },
      {
        id: 'relation-rel-output-target',
        eyebrow: 'Provenance',
        title: 'produced',
        detail: 'output -> target · plan oap-global',
        status: 'ready',
        kind: 'result',
        lane: 'outputs',
      },
      {
        id: 'output-object-global',
        eyebrow: 'Output object',
        title: 'generated_asset asset_global',
        detail: 'mindscape://fixture_pack/generated_asset/asset_global',
        status: 'ready',
        kind: 'artifact',
        lane: 'artifacts',
      },
    ],
    edges: [
      {
        id: 'edge-command-run',
        from_id: 'command-oap-global',
        to_id: 'run-task-global',
        type: 'dispatches',
      },
      {
        id: 'edge-run-closure',
        from_id: 'run-task-global',
        to_id: 'closure-oap-global',
        type: 'closes',
      },
      {
        id: 'edge-closure-output',
        from_id: 'closure-oap-global',
        to_id: 'output-object-global',
        type: 'produced',
      },
    ],
    task_count: 1,
    relation_count: 2,
    artifact_count: 1,
  }), {
    status: 200,
    headers: jsonHeaders,
  });
}

export function createEmptyExecutionGraphResponse(): Response {
  return new Response(JSON.stringify({
    workspace_id: 'ws-global',
    nodes: [],
    edges: [],
    task_count: 0,
    relation_count: 0,
    artifact_count: 0,
  }), {
    status: 200,
    headers: jsonHeaders,
  });
}
