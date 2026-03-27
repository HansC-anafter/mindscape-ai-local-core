import { describe, expect, it } from 'vitest';
import { adaptMemoryImpactGraph } from '../memory-impact-graph/adapter';
import type { MemoryImpactGraphResponse } from '../memory-impact-graph/types';

const sampleResponse: MemoryImpactGraphResponse = {
  workspace_id: 'ws-test',
  session_id: 'session-1',
  focus: {
    workspace_id: 'ws-test',
    session_id: 'session-1',
    focus_node_id: 'meeting_session:session-1',
    execution_ids: ['exec-1'],
  },
  packet_summary: {
    selected_node_count: 2,
    route_sections: ['verified_knowledge', 'active_goals'],
    counts_by_type: {
      session: 1,
      knowledge: 1,
      goal: 1,
      memory_item: 1,
      execution: 1,
    },
    selection: {},
  },
  nodes: [
    {
      id: 'meeting_session:session-1',
      type: 'session',
      label: 'Meeting Session session-1',
      subtitle: 'general',
      status: 'closed',
      metadata: {},
    },
    {
      id: 'knowledge:knowledge-1',
      type: 'knowledge',
      label: 'Governed continuity first',
      subtitle: 'principle',
      status: 'verified',
      metadata: {
        packet_layer: 'knowledge.verified',
      },
    },
    {
      id: 'goal:goal-1',
      type: 'goal',
      label: 'Ship partner demo',
      subtitle: 'Quarter horizon',
      status: 'active',
      metadata: {
        packet_layer: 'goals.active',
      },
    },
    {
      id: 'execution:exec-1',
      type: 'execution',
      label: 'Execution exec-1',
      subtitle: 'workspace task',
      metadata: {
        execution_id: 'exec-1',
      },
    },
    {
      id: 'memory_item:memory-1',
      type: 'memory_item',
      label: 'Canonical Memory',
      subtitle: 'Validated meeting closure',
      status: 'active',
      metadata: {
        memory_item_id: 'memory-1',
        verification_status: 'verified',
      },
    },
  ],
  edges: [
    {
      id: 'selected-knowledge',
      from_node_id: 'meeting_session:session-1',
      to_node_id: 'knowledge:knowledge-1',
      kind: 'selected_for_context',
      provenance: 'explicit',
      metadata: {},
    },
    {
      id: 'selected-goal',
      from_node_id: 'meeting_session:session-1',
      to_node_id: 'goal:goal-1',
      kind: 'selected_for_context',
      provenance: 'explicit',
      metadata: {},
    },
    {
      id: 'produced-execution',
      from_node_id: 'meeting_session:session-1',
      to_node_id: 'execution:exec-1',
      kind: 'produced',
      provenance: 'explicit',
      metadata: {},
    },
    {
      id: 'writeback',
      from_node_id: 'meeting_session:session-1',
      to_node_id: 'memory_item:memory-1',
      kind: 'writes_back_to',
      provenance: 'explicit',
      metadata: {},
    },
    {
      id: 'inferred-link',
      from_node_id: 'goal:goal-1',
      to_node_id: 'memory_item:memory-1',
      kind: 'derived_from',
      provenance: 'inferred',
      metadata: {},
    },
  ],
  warnings: [],
};

describe('adaptMemoryImpactGraph', () => {
  it('marks focus, selected, produced, and writeback nodes with the expected emphasis', () => {
    const adapted = adaptMemoryImpactGraph(sampleResponse);

    expect(adapted.defaultSelectedNodeId).toBe('memory_item:memory-1');

    const focusNode = adapted.nodes.find((node) => node.id === 'meeting_session:session-1');
    const selectedNode = adapted.nodes.find((node) => node.id === 'knowledge:knowledge-1');
    const producedNode = adapted.nodes.find((node) => node.id === 'execution:exec-1');
    const writebackNode = adapted.nodes.find((node) => node.id === 'memory_item:memory-1');

    expect(focusNode?.emphasis).toBe('focus');
    expect(selectedNode?.emphasis).toBe('selected');
    expect(producedNode?.emphasis).toBe('produced');
    expect(writebackNode?.emphasis).toBe('produced');
    expect(selectedNode?.isSelected).toBe(true);
  });

  it('assigns edge styles based on kind and provenance', () => {
    const adapted = adaptMemoryImpactGraph(sampleResponse);

    const selectedEdge = adapted.edges.find((edge) => edge.kind === 'selected_for_context');
    const writebackEdge = adapted.edges.find((edge) => edge.kind === 'writes_back_to');
    const inferredEdge = adapted.edges.find((edge) => edge.provenance === 'inferred');

    expect(selectedEdge?.size).toBe(3.2);
    expect(writebackEdge?.size).toBe(3.6);
    expect(inferredEdge?.size).toBe(1.2);
    expect(writebackEdge?.color).toBe('#059669');
  });
});
