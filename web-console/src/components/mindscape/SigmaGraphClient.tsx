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
    console.log('[LoadGraph] Loading graph with', nodes.length, 'nodes and', edges.length, 'edges');
    const graph = new Graph();

    nodes.forEach((node, index) => {
      const isHighlighted = activeLens === 'all' || node.category === activeLens;

      // Calculate positions in a circle with much better spacing
      // Use a larger radius for better initial visibility
      const angle = (2 * Math.PI * index) / Math.max(nodes.length, 1);
      const radius = 150; // Fixed radius for consistent layout
      const x = Math.cos(angle) * radius;
      const y = Math.sin(angle) * radius;

      console.log(`[LoadGraph] Node ${index + 1}/${nodes.length}: angle=${angle.toFixed(2)}, radius=${radius}, position=(${x.toFixed(2)}, ${y.toFixed(2)})`);

      // Ensure minimum size for visibility (database size is 1.0, which is too small)
      const nodeSize = node.size && node.size > 1 ? node.size : 20;
      const nodeData = {
        label: `${node.icon || ''} ${node.label}`,
        x,
        y,
        size: isHighlighted ? nodeSize : Math.max(nodeSize * 0.6, 12), // At least 12px when not highlighted
        color: isHighlighted ? (TYPE_COLORS[node.node_type] || '#94a3b8') : '#d1d5db',
        nodeType: node.node_type,
        category: node.category,
        description: node.description,
        originalColor: TYPE_COLORS[node.node_type] || '#94a3b8',
        originalSize: nodeSize,
      };

      console.log('[LoadGraph] Adding node:', node.id, nodeData);
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
    console.log('[LoadGraph] Graph loaded with', graph.order, 'nodes and', graph.size, 'edges');

    // Auto-fit camera to show all nodes after graph is loaded
    // Use requestAnimationFrame to ensure graph is fully rendered
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

            // If all nodes are at origin, use default view
            if (bounds.minX === Infinity || bounds.maxX === -Infinity) {
              console.log('[LoadGraph] All nodes at origin, using default camera');
              return;
            }

            // Calculate center point - ensure it's exactly centered
            const centerX = (bounds.minX + bounds.maxX) / 2;
            const centerY = (bounds.minY + bounds.maxY) / 2;
            const width = bounds.maxX - bounds.minX;
            const height = bounds.maxY - bounds.minY;

            // Dynamically calculate ratio based on actual node bounds
            // In Sigma.js, ratio represents the zoom level (smaller = more zoomed in)
            // We need to calculate ratio so that all nodes fit in the viewport

            // Calculate the maximum distance from center to any node
            let maxDistanceFromCenter = 0;
            graph.forEachNode((nodeId, attributes) => {
              const x = attributes.x || 0;
              const y = attributes.y || 0;
              const distance = Math.sqrt(
                Math.pow(x - centerX, 2) + Math.pow(y - centerY, 2)
              );
              maxDistanceFromCenter = Math.max(maxDistanceFromCenter, distance);
            });

            // Get the container dimensions (approximate, Sigma.js uses these internally)
            // For a 600px height container, we want to show nodes within that space
            // Ratio needs to be calculated based on the viewport size and node spread
            const containerHeight = 600; // Approximate container height
            const containerWidth = 1200; // Approximate container width
            const viewportSize = Math.min(containerWidth, containerHeight);

            // We want the visible area to be at least maxDistanceFromCenter * 2 (diameter) + padding
            const padding = 1.3; // 30% padding
            const requiredVisibleSize = maxDistanceFromCenter * 2 * padding;

            // Ratio is approximately: viewportSize / (requiredVisibleSize / 2)
            // But this is simplified - actual calculation depends on Sigma's internal scaling
            // Based on user's adjustment, ratio around 1.73 works for radius 150
            // So for radius 150, ratio should be around 1.73
            // Let's use a proportional calculation
            const baseRadius = 150;
            const baseRatio = 1.73; // User's preferred ratio for radius 150
            const calculatedRatio = (maxDistanceFromCenter / baseRadius) * baseRatio;

            // Ensure reasonable bounds
            const finalRatio = Math.max(Math.min(calculatedRatio, 5.0), 0.5);

            console.log('[LoadGraph] Camera bounds (dynamic calculation):', {
              minX: bounds.minX.toFixed(2),
              maxX: bounds.maxX.toFixed(2),
              minY: bounds.minY.toFixed(2),
              maxY: bounds.maxY.toFixed(2),
              width: width.toFixed(2),
              height: height.toFixed(2),
              centerX: centerX.toFixed(2),
              centerY: centerY.toFixed(2),
              calculatedRatio: calculatedRatio.toFixed(2),
              finalRatio: finalRatio.toFixed(2),
              visibleWidth: (finalRatio * 2).toFixed(2),
              visibleHeight: (finalRatio * 2).toFixed(2),
            });

            // Use goTo for smooth camera transition, or setState for immediate
            if (camera.goTo) {
              camera.goTo({
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

            // Force a refresh to ensure the camera state is applied
            sigma.refresh();

            console.log('[LoadGraph] Camera auto-adjusted to center:', centerX.toFixed(2), centerY.toFixed(2), 'ratio:', finalRatio.toFixed(2));
          } catch (error) {
            console.error('[LoadGraph] Error adjusting camera:', error);
          }
        }
      }, 300); // Increased delay to ensure graph is fully loaded and rendered
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
    registerEvents({
      nodeClick: ({ node }) => {
        const attributes = sigma.getGraph().getNodeAttributes(node);
        onNodeClick?.(node, attributes);
      },
    });
  }, [registerEvents, onNodeClick, sigma]);
  return null;
}

// Component to monitor camera changes and auto-adjust when graph changes
function CameraMonitor() {
  const sigma = useSigma();

  useEffect(() => {
    const camera = sigma.getCamera();
    const graph = sigma.getGraph();

    // Auto-adjust camera when graph structure changes (e.g., after ForceAtlas2 layout)
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

      // Calculate the maximum distance from center to any node
      let maxDistanceFromCenter = 0;
      graph.forEachNode((nodeId, attributes) => {
        const x = attributes.x || 0;
        const y = attributes.y || 0;
        const distance = Math.sqrt(
          Math.pow(x - centerX, 2) + Math.pow(y - centerY, 2)
        );
        maxDistanceFromCenter = Math.max(maxDistanceFromCenter, distance);
      });

      // Use proportional calculation based on user's preferred ratio
      const baseRadius = 150;
      const baseRatio = 1.73; // User's preferred ratio for radius 150
      const calculatedRatio = (maxDistanceFromCenter / baseRadius) * baseRatio;
      const finalRatio = Math.max(Math.min(calculatedRatio, 5.0), 0.5);

      // Only adjust if the change is significant (avoid constant micro-adjustments)
      const currentState = camera.getState();
      const distance = Math.sqrt(
        Math.pow(currentState.x - centerX, 2) + Math.pow(currentState.y - centerY, 2)
      );
      const ratioDiff = Math.abs(currentState.ratio - finalRatio);

      // Only adjust if change is significant (more than 10% difference or position moved > 10 units)
      if (distance > 10 || ratioDiff > currentState.ratio * 0.1) {
        if (camera.goTo) {
          camera.goTo({
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
        console.log('[CameraMonitor] Auto-adjusted camera (dynamic):', {
          center: `(${centerX.toFixed(2)}, ${centerY.toFixed(2)})`,
          ratio: finalRatio.toFixed(2),
          reason: distance > 10 ? 'position changed' : 'ratio changed',
        });
      }
    };

    // Listen for graph changes (nodes moved, added, etc.)
    // Use debounce to avoid too frequent updates
    let debounceTimer: NodeJS.Timeout | null = null;
    const debouncedAutoAdjust = () => {
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(autoAdjustCamera, 500); // Wait 500ms after last change
    };

    graph.on('nodeUpdated', debouncedAutoAdjust);
    graph.on('nodeAdded', debouncedAutoAdjust);

    // Also log camera changes for debugging (optional, can be removed)
    const handleCameraChange = () => {
      // Only log if needed for debugging
    };

    camera.on('updated', handleCameraChange);

    return () => {
      if (debounceTimer) clearTimeout(debounceTimer);
      graph.off('nodeUpdated', debouncedAutoAdjust);
      graph.off('nodeAdded', debouncedAutoAdjust);
      camera.off('updated', handleCameraChange);
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

  // Debug logging
  console.log('[SigmaGraphClient] Props:', { activeLens, workspaceId });
  console.log('[SigmaGraphClient] State:', { nodesCount: nodes.length, edgesCount: edges.length, isLoading, isError });
  console.log('[SigmaGraphClient] Nodes:', nodes);
  console.log('[SigmaGraphClient] Edges:', edges);

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
    console.log('[SigmaGraphClient] Rendering: Loading state');
    return (
      <div className="w-full h-[600px] bg-gray-100 rounded-lg animate-pulse flex items-center justify-center">
        <span className="text-gray-400">{t('loading')}</span>
      </div>
    );
  }

  if (isError) {
    console.log('[SigmaGraphClient] Rendering: Error state');
    return (
      <div className="w-full h-[600px] bg-red-50 rounded-lg flex flex-col items-center justify-center">
        <span className="text-red-600 text-lg mb-2">{t('errorLoadingGraph')}</span>
      </div>
    );
  }

  if (nodes.length === 0) {
    console.log('[SigmaGraphClient] Rendering: null (no nodes, handled by parent)');
    return null; // Empty state is handled by parent
  }

  console.log('[SigmaGraphClient] Rendering: SigmaContainer with', nodes.length, 'nodes and', edges.length, 'edges');
  console.log('[SigmaGraphClient] Settings:', settings);

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

