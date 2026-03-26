'use client';

import React, { useEffect, useMemo } from 'react';
import Graph from 'graphology';
import {
  SigmaContainer,
  useLoadGraph,
  useRegisterEvents,
  useSigma,
} from '@react-sigma/core';
import '@react-sigma/core/lib/style.css';
import { ForceAtlas2Layout } from '@/components/mindscape/GraphWithLayout';
import type {
  MemoryImpactVisualEdge,
  MemoryImpactVisualNode,
} from './types';

function LoadMemoryImpactGraph({
  nodes,
  edges,
}: {
  nodes: MemoryImpactVisualNode[];
  edges: MemoryImpactVisualEdge[];
}) {
  const loadGraph = useLoadGraph();
  const sigma = useSigma();

  useEffect(() => {
    const graph = new Graph({ multi: true });

    nodes.forEach((node) => {
      graph.addNode(node.id, {
        label: node.label,
        x: node.x,
        y: node.y,
        size: node.size,
        color: node.color,
      });
    });

    edges.forEach((edge) => {
      if (graph.hasNode(edge.from_node_id) && graph.hasNode(edge.to_node_id)) {
        graph.addEdgeWithKey(edge.id, edge.from_node_id, edge.to_node_id, {
          color: edge.color,
          size: edge.size,
          type: 'line',
        });
      }
    });

    loadGraph(graph);

    requestAnimationFrame(() => {
      const camera = sigma.getCamera();
      camera.setState({
        x: 0,
        y: 0,
        ratio: 1.6,
      });
      sigma.refresh();
    });
  }, [edges, loadGraph, nodes, sigma]);

  return null;
}

function MemoryImpactGraphEvents({
  nodesById,
  onNodeClick,
}: {
  nodesById: Map<string, MemoryImpactVisualNode>;
  onNodeClick: (node: MemoryImpactVisualNode) => void;
}) {
  const registerEvents = useRegisterEvents();

  useEffect(() => {
    registerEvents({
      clickNode: ({ node }) => {
        const next = nodesById.get(node);
        if (next) {
          onNodeClick(next);
        }
      },
    });
  }, [nodesById, onNodeClick, registerEvents]);

  return null;
}

export function MemoryImpactGraphCanvas({
  nodes,
  edges,
  onNodeClick,
  heightClass,
}: {
  nodes: MemoryImpactVisualNode[];
  edges: MemoryImpactVisualEdge[];
  onNodeClick: (node: MemoryImpactVisualNode) => void;
  heightClass: string;
}) {
  const nodesById = useMemo(
    () => new Map(nodes.map((node) => [node.id, node])),
    [nodes]
  );

  return (
    <div className={`overflow-hidden rounded-lg border border-slate-200 bg-white/70 dark:border-slate-700 dark:bg-slate-950/40 ${heightClass}`}>
      <SigmaContainer
        style={{ height: '100%', width: '100%' }}
        settings={{
          renderLabels: true,
          labelDensity: 0.08,
          labelGridCellSize: 80,
          labelRenderedSizeThreshold: 12,
          defaultEdgeType: 'line',
          defaultNodeType: 'circle',
          allowInvalidContainer: true,
          zIndex: true,
        }}
      >
        <LoadMemoryImpactGraph nodes={nodes} edges={edges} />
        <ForceAtlas2Layout autoStart duration={1200} />
        <MemoryImpactGraphEvents nodesById={nodesById} onNodeClick={onNodeClick} />
      </SigmaContainer>
    </div>
  );
}
