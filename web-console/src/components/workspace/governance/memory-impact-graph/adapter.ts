'use client';

import type {
  MemoryImpactGraphResponse,
  MemoryImpactVisualEdge,
  MemoryImpactVisualNode,
} from './types';

const NODE_COLORS: Record<string, string> = {
  session: '#0369a1',
  execution: '#2563eb',
  memory_item: '#0f766e',
  goal: '#16a34a',
  knowledge: '#7c3aed',
  decision: '#d97706',
  action_item: '#dc2626',
  digest: '#0891b2',
  artifact: '#64748b',
};

const EDGE_COLORS: Record<string, string> = {
  selected_for_context: '#0284c7',
  produced: '#64748b',
  writes_back_to: '#059669',
  derived_from: '#d97706',
};

interface AdaptedGraph {
  nodes: MemoryImpactVisualNode[];
  edges: MemoryImpactVisualEdge[];
  defaultSelectedNodeId: string | null;
}

function toRadians(degrees: number): number {
  return (degrees * Math.PI) / 180;
}

function positionArc(
  ids: string[],
  radius: number,
  startDegrees: number,
  endDegrees: number,
  positions: Map<string, { x: number; y: number }>
) {
  if (ids.length === 0) {
    return;
  }

  if (ids.length === 1) {
    const angle = toRadians((startDegrees + endDegrees) / 2);
    positions.set(ids[0], {
      x: Math.cos(angle) * radius,
      y: Math.sin(angle) * radius,
    });
    return;
  }

  const step = (endDegrees - startDegrees) / (ids.length - 1);
  ids.forEach((id, index) => {
    const angle = toRadians(startDegrees + step * index);
    positions.set(id, {
      x: Math.cos(angle) * radius,
      y: Math.sin(angle) * radius,
    });
  });
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

export function adaptMemoryImpactGraph(
  response: MemoryImpactGraphResponse
): AdaptedGraph {
  const focusNodeId = response.focus.focus_node_id;
  const selectedNodeIds = unique(
    response.edges
      .filter(
        (edge) =>
          edge.kind === 'selected_for_context' && edge.from_node_id === focusNodeId
      )
      .map((edge) => edge.to_node_id)
  );
  const writebackNodeIds = unique(
    response.edges
      .filter(
        (edge) =>
          edge.kind === 'writes_back_to' && edge.from_node_id === focusNodeId
      )
      .map((edge) => edge.to_node_id)
  );
  const producedNodeIds = unique(
    response.edges
      .filter((edge) => edge.kind === 'produced' && edge.from_node_id === focusNodeId)
      .map((edge) => edge.to_node_id)
      .filter((nodeId) => !selectedNodeIds.includes(nodeId))
  );

  const secondaryNodeIds = response.nodes
    .map((node) => node.id)
    .filter(
      (nodeId) =>
        nodeId !== focusNodeId &&
        !selectedNodeIds.includes(nodeId) &&
        !producedNodeIds.includes(nodeId) &&
        !writebackNodeIds.includes(nodeId)
    );

  const positions = new Map<string, { x: number; y: number }>();
  positions.set(focusNodeId, { x: 0, y: 0 });
  positionArc(selectedNodeIds, 1.35, 145, 215, positions);
  positionArc(producedNodeIds, 1.35, -20, 50, positions);
  positionArc(writebackNodeIds, 1.05, 285, 340, positions);
  positionArc(secondaryNodeIds, 1.75, 235, 325, positions);

  const nodes: MemoryImpactVisualNode[] = response.nodes.map((node) => {
    const isFocus = node.id === focusNodeId;
    const isSelected = selectedNodeIds.includes(node.id);
    const emphasis: MemoryImpactVisualNode['emphasis'] = isFocus
      ? 'focus'
      : isSelected
        ? 'selected'
        : producedNodeIds.includes(node.id) || writebackNodeIds.includes(node.id)
          ? 'produced'
          : 'secondary';

    const position = positions.get(node.id) || { x: 0, y: 0 };
    const baseSize =
      emphasis === 'focus'
        ? 22
        : emphasis === 'selected'
          ? 18
          : emphasis === 'produced'
            ? 15
            : 13;

    return {
      ...node,
      x: position.x,
      y: position.y,
      size: baseSize,
      color: NODE_COLORS[node.type] || '#64748b',
      emphasis,
      isFocus,
      isSelected,
    };
  });

  const edges: MemoryImpactVisualEdge[] = response.edges.map((edge) => ({
    ...edge,
    color: EDGE_COLORS[edge.kind] || '#94a3b8',
    size:
      edge.kind === 'writes_back_to'
        ? 3.6
        : edge.kind === 'selected_for_context'
          ? 3.2
          : edge.provenance === 'inferred'
            ? 1.2
            : 2,
  }));

  const defaultSelectedNodeId =
    writebackNodeIds[0] || selectedNodeIds[0] || focusNodeId || null;

  return {
    nodes,
    edges,
    defaultSelectedNodeId,
  };
}
