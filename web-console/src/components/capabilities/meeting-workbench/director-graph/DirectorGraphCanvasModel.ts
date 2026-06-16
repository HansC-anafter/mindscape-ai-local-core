import type { Edge, Node } from '@xyflow/react';

import type {
  CompositionGraphDiagnostic,
  CompositionGraphEdge,
  CompositionGraphImportExportPayload,
  CompositionGraphNode,
  CompositionGraphNodeType,
  CompositionGraphRun,
  CompositionGraphRunNodeStatus,
  CompositionGraphViewport,
} from '@/lib/composition-graph';

export type DirectorGraphNodeData = {
  graphNode: CompositionGraphNode;
  nodeType: CompositionGraphNodeType;
  runStatus?: CompositionGraphRunNodeStatus;
};
export type DirectorGraphFlowNode = Node<DirectorGraphNodeData>;
export type DirectorGraphFlowEdge = Edge<{ graphEdge: CompositionGraphEdge }>;

export const INITIAL_VIEWPORT: CompositionGraphViewport = { x: 0, y: 0, zoom: 1 };

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function getUnknownNodeType(id: string): CompositionGraphNodeType {
  return {
    id,
    label: id,
    source: 'pack',
    input_ports: [{ id: 'input', direction: 'input', data_type: 'any' }],
    output_ports: [{ id: 'output', direction: 'output', data_type: 'any' }],
  };
}

export function defaultValueForSchema(schema: unknown): unknown {
  if (!isRecord(schema)) {
    return '';
  }
  const type = schema.type;
  if (type === 'object') {
    const properties = isRecord(schema.properties) ? schema.properties : {};
    const required = Array.isArray(schema.required) ? schema.required.filter((item): item is string => typeof item === 'string') : [];
    return required.reduce<Record<string, unknown>>((payload, key) => {
      payload[key] = defaultValueForSchema(properties[key]);
      return payload;
    }, {});
  }
  if (type === 'array') {
    return [];
  }
  if (type === 'number' || type === 'integer') {
    return 0;
  }
  if (type === 'boolean') {
    return false;
  }
  return '';
}

export function buildDefaultPayload(nodeType: CompositionGraphNodeType, nodeId: string, workspaceId: string): Record<string, unknown> {
  if (nodeType.id === 'object_reference') {
    return {
      ref: {
        uri: `mindscape://object/${nodeId}`,
        owner_pack: 'workspace',
        object_kind: 'object',
        object_id: nodeId,
        workspace_id: workspaceId,
      },
    };
  }
  const schemaPayload = defaultValueForSchema(nodeType.payload_schema);
  return isRecord(schemaPayload) ? schemaPayload : {};
}

export function nodeTypePorts(nodeType: CompositionGraphNodeType, direction: 'input' | 'output') {
  const ports = direction === 'input' ? nodeType.input_ports || [] : nodeType.output_ports || [];
  return ports.length > 0 ? ports : [{ id: direction, direction, data_type: 'any' }];
}

export function dataTypesCompatible(sourceType: string, targetType: string): boolean {
  return sourceType === targetType || sourceType === 'any' || targetType === 'any';
}

export function toFlowNodes(
  graphNodes: CompositionGraphNode[],
  nodeTypeById: Map<string, CompositionGraphNodeType>,
  run?: CompositionGraphRun | null,
): DirectorGraphFlowNode[] {
  return graphNodes.map((graphNode) => {
    const nodeType = nodeTypeById.get(graphNode.type) || getUnknownNodeType(graphNode.type);
    const runStatus = run?.node_states?.[graphNode.id]?.status;
    return {
      id: graphNode.id,
      type: 'compositionGraphNode',
      position: graphNode.position,
      data: { graphNode, nodeType, runStatus },
    };
  });
}

export function toFlowEdges(graphEdges: CompositionGraphEdge[]): DirectorGraphFlowEdge[] {
  return graphEdges.map((graphEdge) => ({
    id: graphEdge.id,
    source: graphEdge.source,
    target: graphEdge.target,
    sourceHandle: graphEdge.source_port,
    targetHandle: graphEdge.target_port,
    type: 'smoothstep',
    data: { graphEdge },
  }));
}

export function toGraphNodes(nodes: DirectorGraphFlowNode[]): CompositionGraphNode[] {
  return nodes.map((node) => ({
    ...node.data.graphNode,
    position: node.position,
    payload: { ...node.data.graphNode.payload },
    metadata: { ...(node.data.graphNode.metadata || {}) },
  }));
}

export function toGraphEdges(edges: DirectorGraphFlowEdge[]): CompositionGraphEdge[] {
  return edges.map((edge) => ({
    ...(edge.data?.graphEdge || {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      source_port: edge.sourceHandle || 'output',
      target_port: edge.targetHandle || 'input',
      type: 'default',
    }),
    source: edge.source,
    target: edge.target,
    source_port: edge.sourceHandle || edge.data?.graphEdge.source_port || 'output',
    target_port: edge.targetHandle || edge.data?.graphEdge.target_port || 'input',
  }));
}

export function portablePayload({
  graphId,
  selectedPrimaryPack,
  nodes,
  edges,
}: {
  graphId: string;
  selectedPrimaryPack: string | null;
  nodes: CompositionGraphNode[];
  edges: CompositionGraphEdge[];
}): CompositionGraphImportExportPayload {
  return {
    schema_version: 'composition_graph.v1',
    graph_id: graphId,
    title: 'Composition Graph',
    selected_primary_pack: selectedPrimaryPack,
    nodes,
    edges,
    viewport: INITIAL_VIEWPORT,
    metadata: {},
  };
}

export function diagnosticText(diagnostics: CompositionGraphDiagnostic[]): string {
  return diagnostics.map((diagnostic) => `${diagnostic.code}: ${diagnostic.message}`).join('\n');
}
