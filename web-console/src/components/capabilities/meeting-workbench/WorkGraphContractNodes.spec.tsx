import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  coerceExecutionGraphNode,
} from './meetingGraphProjection';
import { MeetingWorkInspectorContent } from './MeetingWorkInspectorPanel';
import { summary } from './meetingWorkbenchTestData';
import type { MeetingNode, MeetingTranslate, RuntimeInspectorSnapshot } from './meetingWorkbenchTypes';

const t: MeetingTranslate = (key) => key;

const runtimeSnapshot: RuntimeInspectorSnapshot = {
  resolvedRuntime: null,
  dispatchChain: [],
  boundRuntimeIds: [],
  agents: [],
  loading: false,
  error: null,
};

const plannerNode: MeetingNode = {
  id: 'tool-result-task-1',
  eyebrow: 'Tool result',
  title: 'creative_space result',
  detail: '1 result fields',
  status: 'ready',
  kind: 'tool_result',
  lane: 'outputs',
  metadata: {
    resource_kind: 'creative_space',
    effect: 'write',
    planner_contract_binding: {
      binding_id: 'planner_contract:abc123',
      tool_name: 'ig.ig_create_creative_space',
      resource_kind: 'creative_space',
      effect: 'write',
      idempotency: 'idempotency_key',
      approval_required: true,
    },
  },
};

describe('Work graph planner contract nodes', () => {
  it('coerces planner contract execution node kinds from the execution graph API', () => {
    expect(
      coerceExecutionGraphNode({
        id: 'planner-binding-abc',
        title: 'ig.ig_query_references',
        eyebrow: 'Planner contract',
        detail: 'read - reference',
        status: 'ready',
        kind: 'planner_contract_binding',
        lane: 'commands',
      }),
    ).toMatchObject({
      id: 'planner-binding-abc',
      kind: 'planner_contract_binding',
      lane: 'commands',
    });
  });

  it('renders planner contract metadata in the Work inspector', () => {
    render(
      <MeetingWorkInspectorContent
        activeInspector="object"
        selectedNode={plannerNode}
        runtimeSnapshot={runtimeSnapshot}
        workspaceId="ws-global"
        meetingId="mtg_global"
        summary={summary}
        attachResponse={null}
        objectGraphProjections={[]}
        objectGraphLoading={false}
        objectGraphError={null}
        commandImpact={null}
        t={t}
      />,
    );

    const contractBlock = screen.getByTestId('meeting-work-planner-contract-node');
    expect(contractBlock).toHaveTextContent('ig.ig_create_creative_space');
    expect(contractBlock).toHaveTextContent('write');
    expect(contractBlock).toHaveTextContent('creative_space');
    expect(contractBlock).toHaveTextContent('idempotency_key');
    expect(contractBlock).toHaveTextContent('required');
  });
});
