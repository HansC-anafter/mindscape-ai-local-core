import type { CompositionGraphEdge, CompositionGraphNode } from '@/lib/composition-graph';

export interface DirectorGraphSnapshot {
  nodes: CompositionGraphNode[];
  edges: CompositionGraphEdge[];
}

export interface DirectorGraphHistoryState {
  snapshots: DirectorGraphSnapshot[];
  index: number;
}

export function createDirectorGraphSnapshot(
  nodes: CompositionGraphNode[],
  edges: CompositionGraphEdge[],
): DirectorGraphSnapshot {
  return {
    nodes: nodes.map((node) => ({
      ...node,
      position: { ...node.position },
      payload: { ...node.payload },
      metadata: { ...(node.metadata || {}) },
    })),
    edges: edges.map((edge) => ({
      ...edge,
      metadata: { ...(edge.metadata || {}) },
    })),
  };
}

export function createDirectorGraphHistory(
  nodes: CompositionGraphNode[] = [],
  edges: CompositionGraphEdge[] = [],
): DirectorGraphHistoryState {
  return {
    snapshots: [createDirectorGraphSnapshot(nodes, edges)],
    index: 0,
  };
}

export function pushDirectorGraphHistory(
  history: DirectorGraphHistoryState,
  snapshot: DirectorGraphSnapshot,
): DirectorGraphHistoryState {
  const nextSnapshots = history.snapshots.slice(0, history.index + 1);
  nextSnapshots.push(snapshot);
  return {
    snapshots: nextSnapshots.slice(-50),
    index: Math.min(nextSnapshots.length, 50) - 1,
  };
}

export function undoDirectorGraphHistory(history: DirectorGraphHistoryState): DirectorGraphHistoryState {
  return {
    snapshots: history.snapshots,
    index: Math.max(0, history.index - 1),
  };
}

export function redoDirectorGraphHistory(history: DirectorGraphHistoryState): DirectorGraphHistoryState {
  return {
    snapshots: history.snapshots,
    index: Math.min(history.snapshots.length - 1, history.index + 1),
  };
}

export function currentDirectorGraphSnapshot(history: DirectorGraphHistoryState): DirectorGraphSnapshot {
  return history.snapshots[history.index] || { nodes: [], edges: [] };
}
