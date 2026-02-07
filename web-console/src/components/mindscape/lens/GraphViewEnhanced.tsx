'use client';

import React, { useEffect, useState, useRef } from 'react';
import type { LensNode } from '@/lib/lens-api';

const TYPE_COLORS: Record<string, string> = {
  value: '#10b981',
  worldview: '#6366f1',
  aesthetic: '#f59e0b',
  knowledge: '#8b5cf6',
  strategy: '#ef4444',
  role: '#06b6d4',
  rhythm: '#ec4899',
  anti_goal: '#dc2626',
};

const STATE_COLORS: Record<string, string> = {
  off: '#d1d5db',
  keep: '#3b82f6',
  emphasize: '#f59e0b',
};

interface GraphViewEnhancedProps {
  nodes: LensNode[];
  selectedNodes: string[];
  onNodeSelect: (nodeId: string) => void;
  onNodeHover: (nodeId: string | null) => void;
}

interface GraphEventsProps {
  onNodeSelect: (nodeId: string) => void;
  onNodeHover: (nodeId: string | null) => void;
}

export function GraphViewEnhanced({
  nodes,
  selectedNodes,
  onNodeSelect,
  onNodeHover,
}: GraphViewEnhancedProps) {
  const [mounted, setMounted] = useState(false);
  const [SigmaComponents, setSigmaComponents] = useState<any>(null);

  useEffect(() => {
    setMounted(true);
    if (typeof window === 'undefined') return;

    Promise.all([
      import('graphology' as any),
      import('@react-sigma/core'),
      // @ts-ignore - CSS import for styles
      import('@react-sigma/core/lib/style.css').catch(() => null)
    ]).then(([graphology, sigmaCore]) => {
      setSigmaComponents({
        Graph: graphology.default,
        SigmaContainer: sigmaCore.SigmaContainer,
        useLoadGraph: sigmaCore.useLoadGraph,
        useSigma: sigmaCore.useSigma,
        useRegisterEvents: sigmaCore.useRegisterEvents,
      });
    }).catch(err => {
      console.error('Failed to load Sigma components:', err);
    });
  }, []);

  if (!mounted || !SigmaComponents) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <p>Loading graph...</p>
      </div>
    );
  }

  if (!nodes || nodes.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <p>No nodes available</p>
      </div>
    );
  }

  const visibleNodes = nodes.filter(n => n.state !== 'off');

  if (visibleNodes.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        <p>All nodes are disabled</p>
      </div>
    );
  }

  const { SigmaContainer, useLoadGraph, useSigma, useRegisterEvents, Graph } = SigmaComponents;

  // Separate component for event handling
  function GraphEvents({ onNodeSelect, onNodeHover }: GraphEventsProps) {
    const registerEvents = useRegisterEvents();
    const sigma = useSigma();
    const unregisterRef = useRef<(() => void) | null>(null);
    const onNodeSelectRef = useRef(onNodeSelect);
    const onNodeHoverRef = useRef(onNodeHover);

    // Keep the refs updated with the latest callbacks
    useEffect(() => {
      onNodeSelectRef.current = onNodeSelect;
      onNodeHoverRef.current = onNodeHover;
    }, [onNodeSelect, onNodeHover]);

    useEffect(() => {
      if (!sigma || !registerEvents) {
        return;
      }

      // Clean up previous registration if exists
      if (unregisterRef.current) {
        unregisterRef.current();
        unregisterRef.current = null;
      }

      const unregister = registerEvents({
        // Click events: lock the node detail panel
        clickNode: (event: any) => {
          const nodeId = event.node || event;
          if (nodeId) {
            onNodeSelectRef.current(nodeId);
          }
        },
        nodeClick: ({ node }: any) => {
          if (node) {
            onNodeSelectRef.current(node);
          }
        },
        // Hover events: temporary preview (always works, even with locked node)
        enterNode: ({ node }: any) => {
          if (node) {
            onNodeHoverRef.current(node);
          }
        },
        leaveNode: () => {
          onNodeHoverRef.current(null);
        },
      });

      // Only store unregister if it's a function
      if (typeof unregister === 'function') {
        unregisterRef.current = unregister;
      }

      return () => {
        if (unregisterRef.current) {
          unregisterRef.current();
          unregisterRef.current = null;
        }
      };
    }, [registerEvents, sigma]);

    return null;
  }

  function LoadGraphInner({ nodes, selectedNodes, onNodeSelect, onNodeHover }: GraphViewEnhancedProps) {
    const loadGraph = useLoadGraph();
    const sigma = useSigma();
    const nodesHashRef = useRef<string>('');
    const cameraStateRef = useRef<{ x: number; y: number; ratio: number } | null>(null);
    const isInitialLoadRef = useRef(true);

    // Only reload graph when nodes actually change (by comparing node IDs)
    useEffect(() => {
      const nodeIds = nodes.filter(n => n.state !== 'off').map(n => n.node_id).sort().join(',');
      if (nodeIds === nodesHashRef.current && !isInitialLoadRef.current) {
        // Nodes haven't changed, only update node styles
        return;
      }
      nodesHashRef.current = nodeIds;
      isInitialLoadRef.current = false;

      // Save current camera state before reloading
      if (sigma && cameraStateRef.current === null) {
        try {
          const camera = sigma.getCamera();
          const state = camera.getState();
          cameraStateRef.current = { x: state.x, y: state.y, ratio: state.ratio };
        } catch (e) {
          // Ignore if camera not ready
        }
      }

      const graph = new Graph();

      // Calculate layout: place nodes in a circle centered at (0, 0)
      const visibleNodesList = nodes.filter(n => n.state !== 'off');
      const nodeCount = visibleNodesList.length;

      nodes.forEach((node, index) => {
        if (node.state === 'off') return; // Skip off nodes

        // Find the index in visible nodes list
        const visibleIndex = visibleNodesList.findIndex(n => n.node_id === node.node_id);
        if (visibleIndex === -1) return;

        // Place nodes in a circle centered at (0, 0)
        // This ensures the graph center is at (0, 0) which matches Sigma.js default camera
        const angle = nodeCount > 1 ? (2 * Math.PI * visibleIndex) / nodeCount : 0;
        // Calculate radius based on container size to ensure nodes fit
        // Use a reasonable default radius that will be adjusted by camera zoom
        const radius = nodeCount > 1 ? 200 : 0;
        const x = Math.cos(angle) * radius;
        const y = Math.sin(angle) * radius;

        const nodeSize = node.state === 'emphasize' ? 25 : 20;
        const isSelected = selectedNodes.includes(node.node_id);
        const baseColor = TYPE_COLORS[node.node_type] || '#94a3b8';
        const stateColor = STATE_COLORS[node.state] || baseColor;

        graph.addNode(node.node_id, {
          label: node.node_label,
          x,
          y,
          size: isSelected ? nodeSize * 1.3 : nodeSize,
          color: isSelected ? '#ef4444' : stateColor,
          nodeType: node.node_type,
          category: node.category,
          state: node.state,
          effective_scope: node.effective_scope,
          isSelected,
        });
      });

      loadGraph(graph);

      // Restore camera state or set initial zoom
      requestAnimationFrame(() => {
        setTimeout(() => {
          if (sigma) {
            try {
              const currentGraph = sigma.getGraph();
              if (currentGraph.order === 0) return;

              const camera = sigma.getCamera();

              // Restore saved camera state if available
              if (cameraStateRef.current) {
                camera.setState(cameraStateRef.current);
                cameraStateRef.current = null; // Clear after restore
              } else {
                // Initial load: adjust zoom to fit all nodes
                const container = sigma.getContainer();
                const bounds = {
                  minX: Infinity,
                  maxX: -Infinity,
                  minY: Infinity,
                  maxY: -Infinity,
                };

                currentGraph.forEachNode((nodeId: string, attributes: any) => {
                  const x = attributes.x || 0;
                  const y = attributes.y || 0;
                  bounds.minX = Math.min(bounds.minX, x);
                  bounds.maxX = Math.max(bounds.maxX, x);
                  bounds.minY = Math.min(bounds.minY, y);
                  bounds.maxY = Math.max(bounds.maxY, y);
                });

                const width = bounds.maxX - bounds.minX || 300;
                const height = bounds.maxY - bounds.minY || 300;
                const padding = 50;
                const containerWidth = container.clientWidth || 800;
                const containerHeight = container.clientHeight || 600;

                const scaleX = width > 0 ? (containerWidth - padding * 2) / width : 1;
                const scaleY = height > 0 ? (containerHeight - padding * 2) / height : 1;
                const scale = Math.min(scaleX, scaleY, 1.5);

                const currentState = camera.getState();
                const newRatio = 1 / scale;
                if (Math.abs(currentState.ratio - newRatio) > 0.01) {
                  camera.setState({ ratio: newRatio });
                }
              }
            } catch (e) {
              // Ignore camera errors
            }
          }
        }, 100);
      });
    }, [nodes, loadGraph, sigma, Graph]);

    // Update node styles when selectedNodes changes (without reloading graph)
    useEffect(() => {
      if (!sigma) return;

      const currentGraph = sigma.getGraph();
      if (currentGraph.order === 0) return;

      currentGraph.forEachNode((nodeId: string, attributes: any) => {
        const node = nodes.find(n => n.node_id === nodeId);
        if (!node || node.state === 'off') return;

        const isSelected = selectedNodes.includes(nodeId);
        const nodeSize = node.state === 'emphasize' ? 25 : 20;
        const baseColor = TYPE_COLORS[node.node_type] || '#94a3b8';
        const stateColor = STATE_COLORS[node.state] || baseColor;

        // Update node attributes without reloading graph
        currentGraph.setNodeAttribute(nodeId, 'size', isSelected ? nodeSize * 1.3 : nodeSize);
        currentGraph.setNodeAttribute(nodeId, 'color', isSelected ? '#ef4444' : stateColor);
        currentGraph.setNodeAttribute(nodeId, 'isSelected', isSelected);
      });

      // Refresh Sigma to show updated styles
      sigma.refresh();
    }, [selectedNodes, nodes, sigma]);

    return null;
  }

  return (
    <div className="h-full w-full">
      <SigmaContainer
        style={{ height: '100%', width: '100%' }}
        settings={{
          renderLabels: true,
          labelFont: 'Arial',
          labelSize: 12,
          labelWeight: 'bold',
          defaultNodeColor: '#94a3b8',
          defaultEdgeColor: '#e2e8f0',
          minCameraRatio: 0.1,
          maxCameraRatio: 10,
          enableEdgeHoverEvents: true,
          enableEdgeClickEvents: true,
          enableNodeHoverEvents: true,
          enableNodeClickEvents: true,
        }}
      >
        <LoadGraphInner
          nodes={nodes}
          selectedNodes={selectedNodes}
          onNodeSelect={onNodeSelect}
          onNodeHover={onNodeHover}
        />
        <GraphEvents
          onNodeSelect={onNodeSelect}
          onNodeHover={onNodeHover}
        />
      </SigmaContainer>
    </div>
  );
}
