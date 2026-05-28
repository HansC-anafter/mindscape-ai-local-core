import React from 'react';

export const MarkerType = {
  ArrowClosed: 'arrowclosed',
};

export function Background() {
  return <div data-testid="reactflow-background" />;
}

export function Controls() {
  return <div data-testid="reactflow-controls" />;
}

export default function ReactFlow({
  children,
  edges = [],
  nodes = [],
}: {
  children?: React.ReactNode;
  edges?: unknown[];
  nodes?: unknown[];
}) {
  return (
    <div
      data-testid="reactflow-mock"
      data-edge-count={edges.length}
      data-node-count={nodes.length}
    >
      {children}
    </div>
  );
}
