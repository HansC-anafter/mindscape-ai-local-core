import React from 'react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryImpactGraphPanel } from '../MemoryImpactGraphPanel';

vi.mock('next/dynamic', () => ({
  default: () =>
    function MockMemoryImpactGraphCanvas(props: {
      nodes: Array<{ id: string }>;
      edges: Array<{ id: string }>;
    }) {
      return (
        <div data-testid="memory-impact-canvas">
          {props.nodes.length} nodes / {props.edges.length} edges
        </div>
      );
    },
}));

const sampleResponse = {
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
      id: 'memory_item:memory-1',
      type: 'memory_item',
      label: 'Canonical Memory',
      subtitle: 'Validated meeting closure',
      status: 'active',
      metadata: {
        memory_item_id: 'memory-1',
        verification_status: 'verified',
        summary: 'Validated meeting closure',
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
      id: 'writeback',
      from_node_id: 'meeting_session:session-1',
      to_node_id: 'memory_item:memory-1',
      kind: 'writes_back_to',
      provenance: 'explicit',
      metadata: {},
    },
  ],
  warnings: [],
};

describe('MemoryImpactGraphPanel', () => {
  beforeEach(() => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => sampleResponse,
    } as Response);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('loads and renders memory impact graph summary and default node detail', async () => {
    render(
      <MemoryImpactGraphPanel
        workspaceId="ws-test"
        apiUrl="http://api.test"
        sessionId="session-1"
      />
    );

    expect(screen.getByText('Selected Memory Subgraph')).toBeInTheDocument();

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledTimes(1);
    });

    const selectedPacketLabel = await screen.findByText('Selected Packet');
    const selectedPacketCard = selectedPacketLabel.parentElement;
    expect(selectedPacketCard).toHaveTextContent('2');
    expect(selectedPacketCard).toHaveTextContent('nodes selected for task context');
    expect(screen.getByText('verified knowledge')).toBeInTheDocument();
    expect(screen.getByText('active goals')).toBeInTheDocument();
    expect(screen.getByTestId('memory-impact-canvas')).toHaveTextContent(
      '4 nodes / 3 edges'
    );
    expect(screen.getByText('Canonical Memory')).toBeInTheDocument();
    expect(screen.getAllByText('Validated meeting closure').length).toBeGreaterThan(0);
  });
});
