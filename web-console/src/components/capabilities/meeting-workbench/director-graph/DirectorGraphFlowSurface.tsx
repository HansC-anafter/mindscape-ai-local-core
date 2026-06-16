import type { Dispatch, SetStateAction } from 'react';
import { Background, Controls, MiniMap, ReactFlow, type Connection, type NodeTypes } from '@xyflow/react';

import type { CompositionGraphNodeType } from '@/lib/composition-graph';
import type { DirectorGraphFlowEdge, DirectorGraphFlowNode } from './DirectorGraphCanvasModel';

type DirectorGraphFlowSurfaceProps = {
  nodes: DirectorGraphFlowNode[];
  edges: DirectorGraphFlowEdge[];
  nodeTypes: NodeTypes;
  nodeTypeById: Map<string, CompositionGraphNodeType>;
  selectedNodeId: string | null;
  setNodes: Dispatch<SetStateAction<DirectorGraphFlowNode[]>>;
  setSelectedNodeId: (nodeId: string | null) => void;
  addNode: (nodeType: CompositionGraphNodeType, position?: { x: number; y: number }) => void;
  handleConnect: (connection: Connection) => void;
};

export function DirectorGraphFlowSurface({
  nodes,
  edges,
  nodeTypes,
  nodeTypeById,
  selectedNodeId,
  setNodes,
  setSelectedNodeId,
  addNode,
  handleConnect,
}: DirectorGraphFlowSurfaceProps) {
  return (
    <div
      className="min-h-0 flex-1"
      onDragOver={(event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'copy';
      }}
      onDrop={(event) => {
        event.preventDefault();
        const nodeTypeId = event.dataTransfer.getData('application/x-composition-graph-node-type');
        const nodeType = nodeTypeById.get(nodeTypeId);
        if (!nodeType) {
          return;
        }
        const bounds = event.currentTarget.getBoundingClientRect();
        addNode(nodeType, { x: event.clientX - bounds.left - 112, y: event.clientY - bounds.top - 48 });
      }}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={(changes) => {
          setNodes((current) =>
            changes.reduce<DirectorGraphFlowNode[]>((nextNodes, change) => {
              if (change.type === 'position' && change.position) {
                return nextNodes.map((node) =>
                  node.id === change.id ? { ...node, position: change.position || node.position } : node,
                );
              }
              if (change.type === 'select') {
                setSelectedNodeId(change.selected ? change.id : selectedNodeId);
              }
              return nextNodes;
            }, current),
          );
        }}
        onEdgesChange={() => undefined}
        onConnect={handleConnect}
        onNodeClick={(_event, node) => setSelectedNodeId(node.id)}
        fitView
      >
        <Background />
        <MiniMap data-testid="director-graph-minimap" pannable zoomable />
        <Controls />
      </ReactFlow>
    </div>
  );
}
