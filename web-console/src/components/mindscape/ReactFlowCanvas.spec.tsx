import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@xyflow/react', async () => {
  const ReactModule = await vi.importActual<typeof import('react')>('react');
  return {
    ReactFlow: ({ nodes, children }: { nodes: Array<{ id: string; data?: { label?: string } }>; children?: React.ReactNode }) => (
      <div data-testid="reactflow-mock">
        {nodes.map((node) => (
          <div key={node.id} data-testid={`reactflow-node-${node.id}`}>
            {node.data?.label || node.id}
          </div>
        ))}
        {children}
      </div>
    ),
    Controls: () => <div data-testid="reactflow-controls" />,
    Background: () => <div data-testid="reactflow-background" />,
    MiniMap: () => <div data-testid="reactflow-minimap" />,
    useNodesState: (initial: unknown[]) => {
      const [value, setValue] = ReactModule.useState(initial);
      return [value, setValue, vi.fn()];
    },
    useEdgesState: (initial: unknown[]) => {
      const [value, setValue] = ReactModule.useState(initial);
      return [value, setValue, vi.fn()];
    },
    BackgroundVariant: { Dots: 'dots' },
    MarkerType: { ArrowClosed: 'arrowclosed' },
    Position: { Left: 'left', Right: 'right' },
  };
});

import ReactFlowCanvas from './ReactFlowCanvas';

describe('ReactFlowCanvas', () => {
  it('renders the existing Mindscape canvas through the @xyflow/react adapter', () => {
    render(
      <ReactFlowCanvas
        nodes={[
          {
            id: 'intent-1',
            type: 'intent',
            label: 'Plan launch',
            status: 'accepted',
            metadata: {},
            created_at: '2026-05-13T00:00:00Z',
          },
        ]}
        edges={[]}
        pendingNodeIds={new Set()}
      />,
    );

    expect(screen.getByTestId('reactflow-mock')).toBeInTheDocument();
    expect(screen.getByTestId('reactflow-node-node-intent-1')).toHaveTextContent('Plan launch');
  });
});
