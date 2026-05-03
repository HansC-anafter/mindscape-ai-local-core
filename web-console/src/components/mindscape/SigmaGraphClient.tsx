'use client';

import React, { useEffect, useMemo } from 'react';
import Graph from 'graphology';
import { SigmaContainer, useLoadGraph, useRegisterEvents, useSigma } from '@react-sigma/core';
import '@react-sigma/core/lib/style.css';
import { useFullGraph, GraphNode, GraphEdge } from '@/lib/graph-api';
import { useGraphLens } from '@/hooks/useGraphLens';
import { ForceAtlas2Layout } from './GraphWithLayout';
import { t } from '@/lib/i18n';

const TYPE_COLORS: Record<string, string> = {
  value: '#10b981',
  worldview: '#6366f1',
  aesthetic: '#f59e0b',
  knowledge: '#8b5cf6',
  strategy: '#ef4444',
  role: '#06b6d4',
  rhythm: '#ec4899',
};

interface LoadGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  activeLens: 'all' | 'direction' | 'action';
}

function LoadGraph({ nodes, edges, activeLens }: LoadGraphProps) {
  const loadGraph = useLoadGraph();
  const sigma = useSigma();

  useEffect(() => {
    const graph = new Graph();

    nodes.forEach((node, index) => {
      const isHighlighted = activeLens === 'all' || node.category === activeLens;
      const angle = (2 * Math.PI * index) / Math.max(nodes.length, 1);
      const radius = 150;
      const x = Math.cos(angle) * radius;
      const y = Math.sin(angle) * radius;
      const nodeSize = node.size && node.size > 1 ? node.size : 20;
      const nodeData = {
        label: `${node.icon || ''} ${node.label}`,
        x,
        y,
        size: isHighlighted ? nodeSize : Math.max(nodeSize * 0.6, 12),
        color: isHighlighted ? (TYPE_COLORS[node.node_type] || '#94a3b8') : '#d1d5db',
        nodeType: node.node_type,
        category: node.category,
        description: node.description,
        originalColor: TYPE_COLORS[node.node_type] || '#94a3b8',
        originalSize: nodeSize,
      };

      graph.addNode(node.id, nodeData);
    });

    edges.forEach((edge) => {
      if (graph.hasNode(edge.source_node_id) && graph.hasNode(edge.target_node_id)) {
        graph.addEdge(edge.source_node_id, edge.target_node_id, {
          size: 2,
          color: '#e2e8f0',
          label: edge.label,
          type: 'arrow',
        });
      }
    });

    loadGraph(graph);

    requestAnimationFrame(() => {
      setTimeout(() => {
        if (graph.order > 0 && sigma) {
          try {
            const camera = sigma.getCamera();
            const bounds = {
              minX: Infinity,
              maxX: -Infinity,
              minY: Infinity,
              maxY: -Infinity,
            };

            graph.forEachNode((nodeId, attributes) => {
              const x = attributes.x || 0;
              const y = attributes.y || 0;
              bounds.minX = Math.min(bounds.minX, x);
              bounds.maxX = Math.max(bounds.maxX, x);
              bounds.minY = Math.min(bounds.minY, y);
              bounds.maxY = Math.max(bounds.maxY, y);
            });

            if (bounds.minX === Infinity || bounds.maxX === -Infinity) {
              return;
            }

            const centerX = (bounds.minX + bounds.maxX) / 2;
            const centerY = (bounds.minY + bounds.maxY) / 2;

            let maxDistanceFromCenter = 0;
            graph.forEachNode((nodeId, attributes) => {
              const x = attributes.x || 0;
              const y = attributes.y || 0;
              const distance = Math.sqrt(
                Math.pow(x - centerX, 2) + Math.pow(y - centerY, 2)
              );
              maxDistanceFromCenter = Math.max(maxDistanceFromCenter, distance);
            });

            const baseRadius = 150;
            const baseRatio = 1.73;
            const calculatedRatio = (maxDistanceFromCenter / baseRadius) * baseRatio;
            const finalRatio = Math.max(Math.min(calculatedRatio, 5.0), 0.5);

            if ((camera as any).goTo) {
              (camera as any).goTo({
                x: centerX,
                y: centerY,
                ratio: finalRatio,
              });
            } else {
              camera.setState({
                x: centerX,
                y: centerY,
                ratio: finalRatio,
              });
            }

            sigma.refresh();
          } catch {
          }
        }
      }, 300);
    });
  }, [loadGraph, nodes, edges, activeLens, sigma]);

  return null;
}

interface GraphEventsProps {
  onNodeClick?: (nodeId: string, attributes: any) => void;
}

function GraphEvents({ onNodeClick }: GraphEventsProps) {
  const registerEvents = useRegisterEvents();
  const sigma = useSigma();

  useEffect(() => {
    (registerEvents as any)({
      nodeClick: ({ node }: { node: string }) => {
        const attributes = sigma.getGraph().getNodeAttributes(node);
        onNodeClick?.(node, attributes);
      },
    });
  }, [registerEvents, onNodeClick, sigma]);
  return null;
}

function CameraMonitor() {
  const sigma = useSigma();

  useEffect(() => {
    const camera = sigma.getCamera();
    const graph = sigma.getGraph();

    const autoAdjustCamera = () => {
      if (graph.order === 0) return;

      const bounds = {
        minX: Infinity,
        maxX: -Infinity,
        minY: Infinity,
        maxY: -Infinity,
      };

      graph.forEachNode((nodeId, attributes) => {
        const x = attributes.x || 0;
        const y = attributes.y || 0;
        bounds.minX = Math.min(bounds.minX, x);
        bounds.maxX = Math.max(bounds.maxX, x);
        bounds.minY = Math.min(bounds.minY, y);
        bounds.maxY = Math.max(bounds.maxY, y);
      });

      if (bounds.minX === Infinity) return;

      const centerX = (bounds.minX + bounds.maxX) / 2;
      const centerY = (bounds.minY + bounds.maxY) / 2;

      let maxDistanceFromCenter = 0;
      graph.forEachNode((nodeId, attributes) => {
        const x = attributes.x || 0;
        const y = attributes.y || 0;
        const distance = Math.sqrt(
          Math.pow(x - centerX, 2) + Math.pow(y - centerY, 2)
        );
        maxDistanceFromCenter = Math.max(maxDistanceFromCenter, distance);
      });

      const baseRadius = 150;
      const baseRatio = 1.73;
      const calculatedRatio = (maxDistanceFromCenter / baseRadius) * baseRatio;
      const finalRatio = Math.max(Math.min(calculatedRatio, 5.0), 0.5);

      const currentState = camera.getState();
      const distance = Math.sqrt(
        Math.pow(currentState.x - centerX, 2) + Math.pow(currentState.y - centerY, 2)
      );
      const ratioDiff = Math.abs(currentState.ratio - finalRatio);

      if (distance > 10 || ratioDiff > currentState.ratio * 0.1) {
        if ((camera as any).goTo) {
          (camera as any).goTo({
            x: centerX,
            y: centerY,
            ratio: finalRatio,
          });
        } else {
          camera.setState({
            x: centerX,
            y: centerY,
            ratio: finalRatio,
          });
        }
      }
    };

    let debounceTimer: NodeJS.Timeout | null = null;
    const debouncedAutoAdjust = () => {
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(autoAdjustCamera, 500);
    };

    (graph as any).on('nodeUpdated', debouncedAutoAdjust);
    (graph as any).on('nodeAdded', debouncedAutoAdjust);

    return () => {
      if (debounceTimer) clearTimeout(debounceTimer);
      (graph as any).off('nodeUpdated', debouncedAutoAdjust);
      (graph as any).off('nodeAdded', debouncedAutoAdjust);
    };
  }, [sigma]);

  return null;
}

interface GraphLensControllerProps {
  activeLens: 'all' | 'direction' | 'action';
}

function GraphLensController({ activeLens }: GraphLensControllerProps) {
  const { applyLens } = useGraphLens();
  useEffect(() => {
    applyLens(activeLens);
  }, [activeLens, applyLens]);
  return null;
}

interface SigmaGraphClientProps {
  activeLens?: 'all' | 'direction' | 'action';
  onNodeSelect?: (nodeId: string, attributes: any) => void;
  workspaceId?: string;
}

export function SigmaGraphClient({
  activeLens = 'all',
  onNodeSelect,
  workspaceId,
}: SigmaGraphClientProps) {
  const { nodes, edges, isLoading, isError } = useFullGraph(workspaceId);

  const handleNodeClick = (nodeId: string, attributes: any) => {
    const node = nodes.find((n) => n.id === nodeId);
    if (node) {
      onNodeSelect?.(nodeId, {
        ...attributes,
        ...node,
      });
    }
  };

  const settings = useMemo(() => ({
    renderLabels: true,
    labelFont: 'Noto Sans TC, sans-serif',
    labelSize: 12,
    labelWeight: 'normal' as const,
    labelColor: { color: '#374151' },
    defaultEdgeColor: '#e2e8f0',
    edgeLabelFont: 'Noto Sans TC, sans-serif',
    enableEdgeEvents: false,
    zoomToSizeRatioFunction: () => 1,
    hideEdgesOnMove: false,
    hideLabelsOnMove: false,
    minCameraRatio: 0.1,
    maxCameraRatio: 5,
    defaultNodeColor: '#94a3b8',
    defaultEdgeType: 'arrow',
    edgeLabelSize: 10,
    nodeLabelSize: 12,
  }), []);

  if (isLoading) {
    return (
      <div className="w-full h-[600px] bg-gray-100 rounded-lg animate-pulse flex items-center justify-center">
        <span className="text-gray-400">{t('loading' as any)}</span>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="w-full h-[600px] bg-red-50 rounded-lg flex flex-col items-center justify-center">
        <span className="text-red-600 text-lg mb-2">{t('errorLoadingGraph' as any)}</span>
      </div>
    );
  }

  if (nodes.length === 0) {
    return null;
  }

  return (
    <div style={{ width: '100%', height: '600px', border: '1px solid #e5e7eb', borderRadius: '8px', backgroundColor: '#ffffff' }}>
      <SigmaContainer
        style={{ height: '100%', width: '100%' }}
        settings={settings}
      >
        <LoadGraph
          nodes={nodes}
          edges={edges}
          activeLens={activeLens}
        />
        <GraphLensController activeLens={activeLens} />
        <ForceAtlas2Layout autoStart={true} duration={5000} />
        <GraphEvents onNodeClick={handleNodeClick} />
        <CameraMonitor />
      </SigmaContainer>
    </div>
  );
}
