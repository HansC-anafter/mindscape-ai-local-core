'use client';

/**
 * ReactFlowCanvas - Internal React Flow implementation
 *
 * This component is imported dynamically to avoid SSR issues.
 * React Flow is MIT licensed.
 */

import React, { useEffect, useMemo, useCallback } from 'react';
import ReactFlow, {
    Node,
    Edge,
    Controls,
    Background,
    MiniMap,
    useNodesState,
    useEdgesState,
    BackgroundVariant,
    NodeMouseHandler,
    MarkerType,
    Position,
} from 'reactflow';
import 'reactflow/dist/style.css';

import type { MindscapeNode, MindscapeEdge } from '@/lib/mindscape-graph-api';

// ============================================================================
// Constants
// ============================================================================

const NODE_WIDTH = 220;
const NODE_HEIGHT = 80;
const HORIZONTAL_SPACING = 80;
const VERTICAL_SPACING = 40;
const PROJECT_GAP = 120;

// Color mapping for different node types
const NODE_COLORS: Record<string, { background: string; border: string }> = {
    intent: { background: '#faf5ff', border: '#a855f7' },
    execution: { background: '#f0fdf4', border: '#22c55e' },
    artifact: { background: '#fff7ed', border: '#f97316' },
    playbook: { background: '#faf5ff', border: '#8b5cf6' },
    step: { background: '#eff6ff', border: '#3b82f6' },
};

// Edge colors based on type
const EDGE_COLORS: Record<string, string> = {
    temporal: '#9ca3af',
    causal: '#3b82f6',
    dependency: '#8b5cf6',
    spawns: '#22c55e',
    produces: '#f97316',
    refers_to: '#06b6d4',
};

// ============================================================================
// Layout Algorithm
// ============================================================================

function calculateNodePositions(
    nodes: MindscapeNode[],
    edges: MindscapeEdge[]
): Map<string, { x: number; y: number }> {
    const positions = new Map<string, { x: number; y: number }>();

    if (nodes.length === 0) return positions;

    // Group nodes by project_id
    const projectGroups = new Map<string, MindscapeNode[]>();
    nodes.forEach(node => {
        const projectId = node.metadata?.project_id || '__no_project__';
        if (!projectGroups.has(projectId)) {
            projectGroups.set(projectId, []);
        }
        projectGroups.get(projectId)!.push(node);
    });

    // Build adjacency list for each project
    const buildAdjacencyList = (projectNodes: MindscapeNode[]) => {
        const nodeIds = new Set(projectNodes.map(n => n.id));
        const adjacency = new Map<string, string[]>();
        const inDegree = new Map<string, number>();

        projectNodes.forEach(node => {
            adjacency.set(node.id, []);
            inDegree.set(node.id, 0);
        });

        edges.forEach(edge => {
            if (nodeIds.has(edge.from_id) && nodeIds.has(edge.to_id)) {
                adjacency.get(edge.from_id)?.push(edge.to_id);
                inDegree.set(edge.to_id, (inDegree.get(edge.to_id) || 0) + 1);
            }
        });

        return { adjacency, inDegree };
    };

    // Topological sort using BFS (Kahn's algorithm)
    const topologicalSort = (
        projectNodes: MindscapeNode[],
        adjacency: Map<string, string[]>,
        inDegree: Map<string, number>
    ): Map<string, number> => {
        const levels = new Map<string, number>();
        const queue: string[] = [];

        projectNodes.forEach(node => {
            if ((inDegree.get(node.id) || 0) === 0) {
                queue.push(node.id);
                levels.set(node.id, 0);
            }
        });

        while (queue.length > 0) {
            const nodeId = queue.shift()!;
            const currentLevel = levels.get(nodeId) || 0;

            adjacency.get(nodeId)?.forEach(childId => {
                inDegree.set(childId, (inDegree.get(childId) || 1) - 1);
                if (inDegree.get(childId) === 0) {
                    queue.push(childId);
                    levels.set(childId, currentLevel + 1);
                }
            });
        }

        // Handle nodes not in DAG (cycles or disconnected)
        projectNodes.forEach(node => {
            if (!levels.has(node.id)) {
                levels.set(node.id, 0);
            }
        });

        return levels;
    };

    let currentY = 0;

    // Sort project groups (put __no_project__ last)
    const sortedProjectIds = Array.from(projectGroups.keys()).sort((a, b) => {
        if (a === '__no_project__') return 1;
        if (b === '__no_project__') return -1;
        return a.localeCompare(b);
    });

    for (const projectId of sortedProjectIds) {
        const projectNodes = projectGroups.get(projectId)!;
        const { adjacency, inDegree } = buildAdjacencyList(projectNodes);
        const levels = topologicalSort(projectNodes, adjacency, inDegree);

        // Group nodes by level
        const levelGroups = new Map<number, MindscapeNode[]>();
        projectNodes.forEach(node => {
            const level = levels.get(node.id) || 0;
            if (!levelGroups.has(level)) {
                levelGroups.set(level, []);
            }
            levelGroups.get(level)!.push(node);
        });

        // Calculate positions within this project
        let maxLevelHeight = 0;
        const sortedLevels = Array.from(levelGroups.keys()).sort((a, b) => a - b);

        for (const level of sortedLevels) {
            const nodesInLevel = levelGroups.get(level)!;
            const levelHeight = nodesInLevel.length * (NODE_HEIGHT + VERTICAL_SPACING);
            maxLevelHeight = Math.max(maxLevelHeight, levelHeight);

            nodesInLevel.forEach((node, index) => {
                const x = level * (NODE_WIDTH + HORIZONTAL_SPACING);
                const y = currentY + index * (NODE_HEIGHT + VERTICAL_SPACING);
                positions.set(node.id, { x, y });
            });
        }

        currentY += maxLevelHeight + PROJECT_GAP;
    }

    return positions;
}

// ============================================================================
// Props Interface
// ============================================================================

interface ReactFlowCanvasProps {
    nodes: MindscapeNode[];
    edges: MindscapeEdge[];
    pendingNodeIds: Set<string>;
    onNodeSelect?: (node: MindscapeNode | null) => void;
    onNodeContextMenu?: (event: React.MouseEvent, node: MindscapeNode) => void;
}

// ============================================================================
// ReactFlowCanvas Component
// ============================================================================

export default function ReactFlowCanvas({
    nodes: mindscapeNodes,
    edges: mindscapeEdges,
    pendingNodeIds,
    onNodeSelect,
    onNodeContextMenu,
}: ReactFlowCanvasProps) {
    // Calculate node positions
    const nodePositions = useMemo(() => {
        return calculateNodePositions(mindscapeNodes, mindscapeEdges);
    }, [mindscapeNodes, mindscapeEdges]);

    // Convert to React Flow nodes
    const initialNodes: Node[] = useMemo(() => {
        return mindscapeNodes.map((node) => {
            const position = nodePositions.get(node.id) || { x: 0, y: 0 };
            const colors = NODE_COLORS[node.type] || NODE_COLORS.intent;
            const isPending = pendingNodeIds.has(node.id);

            return {
                id: `node-${node.id}`,
                type: 'default',
                position,
                data: {
                    label: node.label,
                    nodeData: node,
                },
                style: {
                    width: NODE_WIDTH,
                    minHeight: NODE_HEIGHT,
                    background: colors.background,
                    border: `2px ${isPending ? 'dashed' : 'solid'} ${colors.border}`,
                    borderRadius: '8px',
                    padding: '12px',
                    fontSize: '12px',
                    fontWeight: 500,
                    color: '#1f2937',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                },
                sourcePosition: Position.Right,
                targetPosition: Position.Left,
            };
        });
    }, [mindscapeNodes, nodePositions, pendingNodeIds]);

    // Convert to React Flow edges
    const initialEdges: Edge[] = useMemo(() => {
        return mindscapeEdges.map((edge) => {
            const color = EDGE_COLORS[edge.type] || EDGE_COLORS.temporal;

            return {
                id: `edge-${edge.id}`,
                source: `node-${edge.from_id}`,
                target: `node-${edge.to_id}`,
                type: 'smoothstep',
                animated: edge.type === 'spawns',
                style: { stroke: color, strokeWidth: 2 },
                markerEnd: {
                    type: MarkerType.ArrowClosed,
                    color: color,
                },
                data: {
                    edgeData: edge,
                },
            };
        });
    }, [mindscapeEdges]);

    // React Flow state
    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

    // Update nodes/edges when data changes
    useEffect(() => {
        setNodes(initialNodes);
    }, [initialNodes, setNodes]);

    useEffect(() => {
        setEdges(initialEdges);
    }, [initialEdges, setEdges]);

    // Handle node click
    const onNodeClick: NodeMouseHandler = useCallback((event, node) => {
        const nodeData = node.data?.nodeData as MindscapeNode | undefined;
        if (nodeData && onNodeSelect) {
            onNodeSelect(nodeData);
        }
    }, [onNodeSelect]);

    // Handle node right-click (context menu)
    const handleNodeContextMenu: NodeMouseHandler = useCallback((event, node) => {
        event.preventDefault();
        const nodeData = node.data?.nodeData as MindscapeNode | undefined;
        if (nodeData && onNodeContextMenu) {
            onNodeContextMenu(event as unknown as React.MouseEvent, nodeData);
        }
    }, [onNodeContextMenu]);

    // Handle background click (deselect)
    const onPaneClick = useCallback(() => {
        if (onNodeSelect) {
            onNodeSelect(null);
        }
    }, [onNodeSelect]);

    console.log('[ReactFlowCanvas] Rendering', nodes.length, 'nodes and', edges.length, 'edges');

    return (
        <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onNodeContextMenu={handleNodeContextMenu}
            onPaneClick={onPaneClick}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            minZoom={0.1}
            maxZoom={2}
            defaultViewport={{ x: 0, y: 0, zoom: 0.5 }}
            attributionPosition="bottom-right"
        >
            <Controls />
            <MiniMap
                nodeColor={(node) => {
                    const nodeData = node.data?.nodeData as MindscapeNode | undefined;
                    const colors = NODE_COLORS[nodeData?.type || 'intent'];
                    return colors.border;
                }}
                maskColor="rgba(255, 255, 255, 0.8)"
            />
            <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
        </ReactFlow>
    );
}

