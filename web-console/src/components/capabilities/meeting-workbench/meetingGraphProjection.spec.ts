import { describe, expect, it } from 'vitest';

import {
  buildCommandImpact,
  buildObjectGraphNodes,
  coerceExecutionGraphEdge,
  coerceExecutionGraphNode,
  collectGraphProjectionRefs,
  projectMeetingGraph,
} from './meetingGraphProjection';
import type {
  MeetingArtifactSummary,
  MeetingEventSummary,
  MeetingGraphEdge,
  MeetingNode,
} from './meetingWorkbenchTypes';

const selectedSummary = {
  ref: {
    uri: 'mindscape://ig/reference/ref_global',
    owner_pack: 'ig',
    object_kind: 'reference',
    object_id: 'ref_global',
  },
  title: 'Global Reference',
  labels: ['ig'],
};

describe('meetingGraphProjection', () => {
  it('coerces execution graph nodes and edges from raw API payloads', () => {
    expect(
      coerceExecutionGraphNode({
        id: 'run-1',
        title: 'Execute pack',
        eyebrow: 'Run',
        detail: 'Running',
        status: 'running',
        kind: 'run',
        lane: 'runs',
        defaultInspector: 'trace',
        metadata: { execution_id: 'exec_1' },
      }),
    ).toMatchObject({
      id: 'run-1',
      title: 'Execute pack',
      status: 'running',
      kind: 'run',
      lane: 'runs',
      defaultInspector: 'trace',
    });
    expect(coerceExecutionGraphNode({ id: 'bad-node', title: 'Missing kind' })).toBeNull();
    expect(
      coerceExecutionGraphNode({
        id: 'command-accepted',
        title: 'Accepted command',
        eyebrow: 'Command',
        detail: 'command accepted',
        status: 'accepted',
        kind: 'command',
        lane: 'commands',
        metadata: { ledger_status: 'accepted' },
      }),
    ).toMatchObject({
      id: 'command-accepted',
      status: 'pending',
      metadata: { ledger_status: 'accepted' },
    });
    expect(
      coerceExecutionGraphNode({
        id: 'command-failed',
        title: 'Failed command',
        eyebrow: 'Command',
        detail: 'command failed',
        status: 'failed',
        kind: 'command',
        lane: 'commands',
      }),
    ).toMatchObject({
      id: 'command-failed',
      status: 'error',
    });

    expect(
      coerceExecutionGraphEdge({
        id: 'edge-1',
        from_id: 'command-1',
        to_id: 'run-1',
        type: 'triggers',
        label: 'triggers',
      }),
    ).toEqual({
      id: 'edge-1',
      from_id: 'command-1',
      to_id: 'run-1',
      type: 'triggers',
      label: 'triggers',
      metadata: undefined,
    });
    expect(coerceExecutionGraphEdge({ id: 'bad-edge', from_id: 'a' })).toBeNull();
  });

  it('deduplicates graph projection refs from summary attachments and staged refs', () => {
    const refs = collectGraphProjectionRefs(selectedSummary, {
      workspace_id: 'ws-global',
      meeting_id: 'mtg_global',
      status: 'attached',
      attachments: [
        {
          role: 'source',
          ref: selectedSummary.ref,
          projection_level: 'meeting',
        },
      ],
      staged_refs: [
        selectedSummary.ref,
        {
          uri: 'mindscape://pd/storyboard/pd_manual',
          owner_pack: 'pd',
          object_kind: 'storyboard',
          object_id: 'pd_manual',
        },
      ],
      review_routes: [],
      errors: [],
    });

    expect(refs).toEqual([
      selectedSummary.ref,
      {
        uri: 'mindscape://pd/storyboard/pd_manual',
        owner_pack: 'pd',
        object_kind: 'storyboard',
        object_id: 'pd_manual',
      },
    ]);
  });

  it('builds object graph nodes and loading/error state nodes', () => {
    const nodes = buildObjectGraphNodes(
      [
        {
          ref: selectedSummary.ref,
          node_kind: 'reference',
          summary: selectedSummary,
          relations: [
            {
              relation_kind: 'derived_from',
              direction: 'outbound',
              target_ref: {
                uri: 'mindscape://pd/storyboard/pd_manual',
                owner_pack: 'pd',
                object_kind: 'storyboard',
                object_id: 'pd_manual',
              },
            },
          ],
        },
      ],
      false,
      null,
    );

    expect(nodes).toHaveLength(1);
    expect(nodes[0]).toMatchObject({
      eyebrow: 'reference',
      title: 'Global Reference',
      detail: '1 bounded relation',
      lane: 'graph',
      defaultInspector: 'graph',
    });

    expect(buildObjectGraphNodes([], true, null)[0]).toMatchObject({
      id: 'object-graph-state',
      title: 'Loading object graph',
      status: 'running',
    });
  });

  it('projects events, artifacts, execution graph nodes, and local tasks into stable lanes', () => {
    const events: MeetingEventSummary[] = [
      {
        id: 'evt-user',
        actor: 'user',
        event_type: 'message',
        timestamp: '2026-05-02T00:00:00Z',
        payload: { message: 'Analyze this reference' },
      },
      {
        id: 'evt-action',
        actor: 'assistant',
        event_type: 'action_item',
        timestamp: '2026-05-02T00:01:00Z',
        payload: { title: 'Run visual audit', execution_id: 'exec_1', status: 'completed' },
      },
      {
        id: 'evt-decision',
        actor: 'assistant',
        event_type: 'decision_final',
        timestamp: '2026-05-02T00:02:00Z',
        payload: { title: 'Approved' },
      },
    ];
    const artifacts: MeetingArtifactSummary[] = [
      {
        id: 'artifact-1',
        title: 'Task Result',
        artifact_type: 'result',
        execution_id: 'exec_1',
        storage_ref: 's3://artifact-1',
      },
    ];
    const localTasks: MeetingNode[] = [
      {
        id: 'task-local',
        eyebrow: 'Pack tool',
        title: 'Local task',
        detail: 'Pending dispatch',
        status: 'running',
        kind: 'run',
        lane: 'runs',
      },
    ];
    const executionNode: MeetingNode = {
      id: 'execution-1',
      eyebrow: 'Execution',
      title: 'Object action',
      detail: 'Executed',
      status: 'ready',
      kind: 'run',
      lane: 'runs',
    };
    const edge: MeetingGraphEdge = {
      id: 'edge-command-run',
      from_id: 'command-evt-user',
      to_id: 'execution-1',
      type: 'triggers',
    };

    const projection = projectMeetingGraph({
      activeMeetingId: 'mtg_global',
      objectKind: 'reference',
      objectTitle: 'Global Reference',
      objectDetail: 'Selected object',
      events,
      artifacts,
      localTasks,
      objectGraphNodes: [],
      artifactsLoading: false,
      artifactsError: null,
      eventsLoading: false,
      eventsError: null,
      executionGraphNodes: [executionNode],
      executionGraphEdges: [edge],
      executionGraphLoading: false,
      executionGraphError: null,
      mode: 'work',
    });

    expect(projection.edges).toEqual([edge]);
    expect(projection.eventCounts).toMatchObject({
      message: 1,
      action_item: 1,
      decision_final: 1,
      executable_action_item: 1,
    });
    expect(projection.nodes.map((node) => node.id)).toEqual(
      expect.arrayContaining([
        'root',
        'object',
        'command-evt-user',
        'run-evt-action',
        'group-decisions',
        'artifact-artifact-1',
        'execution-1',
        'task-local',
        'ready',
      ]),
    );
  });

  it('builds command impact through execution edges and trace fallback', () => {
    const commandNode: MeetingNode = {
      id: 'command-evt-user',
      eyebrow: 'Command',
      title: 'Analyze this reference',
      detail: 'command',
      status: 'pending',
      kind: 'command',
      lane: 'commands',
      eventIds: ['evt-user'],
    };
    const outputNode: MeetingNode = {
      id: 'output-1',
      eyebrow: 'Result',
      title: 'Meeting Minutes',
      detail: 'ready',
      status: 'ready',
      kind: 'result',
      lane: 'outputs',
    };
    const traceEvents: MeetingEventSummary[] = [
      { id: 'evt-user', actor: 'user', event_type: 'message', payload: { message: 'Analyze' } },
      { id: 'evt-assistant', actor: 'assistant', event_type: 'decision_final', payload: { title: 'Approved' } },
    ];

    const impact = buildCommandImpact(
      commandNode,
      [commandNode, outputNode],
      [{ id: 'edge-1', from_id: 'command-evt-user', to_id: 'output-1', type: 'produces' }],
      traceEvents,
    );

    expect(impact).toMatchObject({
      commandText: 'Analyze this reference',
      phase: 'initial',
      status: 'ready',
      outputs: [outputNode],
    });
    expect(Array.from(impact?.edgeIds || [])).toEqual(['edge-1']);
    expect(impact?.decisions).toEqual([]);

    const fallbackImpact = buildCommandImpact(commandNode, [commandNode], [], traceEvents);
    expect(fallbackImpact?.decisions).toEqual([traceEvents[1]]);
  });
});
