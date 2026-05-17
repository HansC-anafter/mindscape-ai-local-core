'use client';

import React, { useMemo, useState } from 'react';
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Copy, Maximize2, Redo2, Save, Trash2, Undo2 } from 'lucide-react';

import {
  fetchCompositionGraphNodeOptions,
  fetchCompositionGraphRun,
  importCompositionGraph,
  runCompositionGraph,
  type CompositionGraphCommandEnvelopeDraft,
  type CompositionGraphDiagnostic,
  type CompositionGraphEdge,
  type CompositionGraphImportExportPayload,
  type CompositionGraphNode,
  type CompositionGraphNodeOption,
  type CompositionGraphRun,
  type CompositionGraphRunNodeStatus,
  type CompositionGraphRunStatus,
  type CompositionGraphNodeType,
  type CompositionGraphViewport,
} from '@/lib/composition-graph';
import type { AddressableObjectRef } from '@/lib/addressable-object-layer';
import type { MeetingMentionItem, MeetingTranslate } from '../meetingWorkbenchTypes';
import { DirectorGraphCompileButton } from './DirectorGraphCompileButton';
import {
  createDirectorGraphHistory,
  createDirectorGraphSnapshot,
  currentDirectorGraphSnapshot,
  pushDirectorGraphHistory,
  redoDirectorGraphHistory,
  type DirectorGraphHistoryState,
  undoDirectorGraphHistory,
} from './DirectorGraphHistory';
import { DirectorGraphImportExport } from './DirectorGraphImportExport';
import { DirectorGraphInspector } from './DirectorGraphInspector';
import { DirectorGraphPalette } from './DirectorGraphPalette';
import { useCompositionGraphContracts } from './useCompositionGraphContracts';
import { useCompositionGraphDraft } from './useCompositionGraphDraft';

type DirectorGraphNodeData = {
  graphNode: CompositionGraphNode;
  nodeType: CompositionGraphNodeType;
  runStatus?: CompositionGraphRunNodeStatus;
};
type DirectorGraphFlowNode = Node<DirectorGraphNodeData>;
type DirectorGraphFlowEdge = Edge<{ graphEdge: CompositionGraphEdge }>;

const INITIAL_VIEWPORT: CompositionGraphViewport = { x: 0, y: 0, zoom: 1 };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function getUnknownNodeType(id: string): CompositionGraphNodeType {
  return {
    id,
    label: id,
    source: 'pack',
    input_ports: [{ id: 'input', direction: 'input', data_type: 'any' }],
    output_ports: [{ id: 'output', direction: 'output', data_type: 'any' }],
  };
}

function defaultValueForSchema(schema: unknown): unknown {
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

function buildDefaultPayload(nodeType: CompositionGraphNodeType, nodeId: string, workspaceId: string): Record<string, unknown> {
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

function nodeTypePorts(nodeType: CompositionGraphNodeType, direction: 'input' | 'output') {
  const ports = direction === 'input' ? nodeType.input_ports || [] : nodeType.output_ports || [];
  return ports.length > 0 ? ports : [{ id: direction, direction, data_type: 'any' }];
}

function dataTypesCompatible(sourceType: string, targetType: string): boolean {
  return sourceType === targetType || sourceType === 'any' || targetType === 'any';
}

function DirectorGraphNodeView({ data, selected }: NodeProps<DirectorGraphFlowNode>) {
  const inputPorts = nodeTypePorts(data.nodeType, 'input');
  const outputPorts = nodeTypePorts(data.nodeType, 'output');
  return (
    <div
      className={`min-h-24 w-56 rounded-md border bg-white px-3 py-2 shadow-sm dark:bg-slate-950 ${
        selected ? 'border-blue-400 ring-2 ring-blue-100 dark:ring-blue-900/40' : 'border-slate-200 dark:border-slate-800'
      }`}
      data-testid={`director-graph-node-${data.graphNode.id}`}
    >
      {inputPorts.map((port, index) => (
        <Handle
          key={port.id}
          id={port.id}
          type="target"
          position={Position.Left}
          style={{ top: `${((index + 1) / (inputPorts.length + 1)) * 100}%` }}
        />
      ))}
      <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
        {data.nodeType.capability_code || data.nodeType.source}
      </div>
      <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{data.nodeType.label}</div>
      <div className="mt-1 flex items-center justify-between gap-2">
        <div className="truncate font-mono text-[11px] text-slate-500 dark:text-slate-400">{data.graphNode.id}</div>
        {data.runStatus ? (
          <span className="shrink-0 rounded-sm bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600 dark:bg-slate-900 dark:text-slate-300">
            {data.runStatus}
          </span>
        ) : null}
      </div>
      {outputPorts.map((port, index) => (
        <Handle
          key={port.id}
          id={port.id}
          type="source"
          position={Position.Right}
          style={{ top: `${((index + 1) / (outputPorts.length + 1)) * 100}%` }}
        />
      ))}
    </div>
  );
}

const nodeTypes = { compositionGraphNode: DirectorGraphNodeView };

function toFlowNodes(
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

function toFlowEdges(graphEdges: CompositionGraphEdge[]): DirectorGraphFlowEdge[] {
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

function toGraphNodes(nodes: DirectorGraphFlowNode[]): CompositionGraphNode[] {
  return nodes.map((node) => ({
    ...node.data.graphNode,
    position: node.position,
    payload: { ...node.data.graphNode.payload },
    metadata: { ...(node.data.graphNode.metadata || {}) },
  }));
}

function toGraphEdges(edges: DirectorGraphFlowEdge[]): CompositionGraphEdge[] {
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

function portablePayload({
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

function diagnosticText(diagnostics: CompositionGraphDiagnostic[]): string {
  return diagnostics.map((diagnostic) => `${diagnostic.code}: ${diagnostic.message}`).join('\n');
}

export function DirectorGraphCanvas({
  apiUrl,
  workspaceId,
  meetingId,
  threadId,
  command,
  selectedPackTool,
  mentionItems = [],
  selectedObjectRef = null,
  onCommandEnvelope,
  t,
}: {
  apiUrl: string;
  workspaceId: string;
  meetingId: string | null;
  threadId: string | null;
  command: string;
  selectedPackTool: string | null;
  mentionItems?: MeetingMentionItem[];
  selectedObjectRef?: AddressableObjectRef | null;
  onCommandEnvelope: (envelope: CompositionGraphCommandEnvelopeDraft) => Promise<void>;
  t: MeetingTranslate;
}) {
  void selectedPackTool;
  void mentionItems;
  void onCommandEnvelope;
  const { contracts, diagnostics, error: contractsError, loading: contractsLoading, nodeTypes: availableNodeTypes } =
    useCompositionGraphContracts({ apiUrl, workspaceId });
  const nodeTypeById = useMemo(
    () => new Map(availableNodeTypes.map((nodeType) => [nodeType.id, nodeType])),
    [availableNodeTypes],
  );
  const [selectedPrimaryPack, setSelectedPrimaryPack] = useState<string | null>(null);
  const selectedContract = useMemo(
    () => contracts.find((contract) => contract.capability_code === selectedPrimaryPack) || contracts[0] || null,
    [contracts, selectedPrimaryPack],
  );
  const defaultEdgeType = selectedContract?.edge_types?.[0]?.id || 'default';
  const [nodes, setNodes] = useState<DirectorGraphFlowNode[]>([]);
  const [edges, setEdges] = useState<DirectorGraphFlowEdge[]>([]);
  const [history, setHistory] = useState<DirectorGraphHistoryState>(() => createDirectorGraphHistory());
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [clipboardNode, setClipboardNode] = useState<CompositionGraphNode | null>(null);
  const [jsonText, setJsonText] = useState('');
  const [importError, setImportError] = useState<string | null>(null);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [payloadText, setPayloadText] = useState('{}');
  const [payloadError, setPayloadError] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<CompositionGraphRunStatus | 'idle'>('idle');
  const [activeRun, setActiveRun] = useState<CompositionGraphRun | null>(null);
  const [runDiagnostics, setRunDiagnostics] = useState<CompositionGraphDiagnostic[]>([]);
  const [comfyLaneOptions, setComfyLaneOptions] = useState<CompositionGraphNodeOption[]>([]);
  const [comfyLaneDiagnostics, setComfyLaneDiagnostics] = useState<CompositionGraphDiagnostic[]>([]);
  const { draft, saveDraft, saveError, saving } = useCompositionGraphDraft({ apiUrl, workspaceId });

  const selectedNode = useMemo(
    () => toGraphNodes(nodes).find((node) => node.id === selectedNodeId) || null,
    [nodes, selectedNodeId],
  );
  const selectedNodeType = selectedNode ? nodeTypeById.get(selectedNode.type) || getUnknownNodeType(selectedNode.type) : null;

  React.useEffect(() => {
    if (!selectedPrimaryPack && contracts.length > 0) {
      setSelectedPrimaryPack(contracts[0].capability_code);
    }
  }, [contracts, selectedPrimaryPack]);

  React.useEffect(() => {
    if (selectedNode) {
      setPayloadText(JSON.stringify(selectedNode.payload || {}, null, 2));
      setPayloadError(null);
    }
  }, [selectedNode]);

  React.useEffect(() => {
    if (!nodeTypeById.has('comfyui_lane_adapter')) {
      return;
    }
    let cancelled = false;
    fetchCompositionGraphNodeOptions(apiUrl, workspaceId, 'comfyui_lane_adapter', 'workflow_ref')
      .then((response) => {
        if (cancelled) {
          return;
        }
        setComfyLaneOptions(response.options || []);
        setComfyLaneDiagnostics(response.diagnostics || []);
      })
      .catch((cause) => {
        if (cancelled) {
          return;
        }
        setComfyLaneOptions([]);
        setComfyLaneDiagnostics([
          {
            code: 'comfyui_ready_lane_not_found',
            message: cause instanceof Error ? cause.message : 'No ready ComfyUI workflow lane is available.',
            severity: 'error',
          },
        ]);
      });
    return () => {
      cancelled = true;
    };
  }, [apiUrl, workspaceId, nodeTypeById]);

  React.useEffect(() => {
    setNodes((current) => toFlowNodes(toGraphNodes(current), nodeTypeById, activeRun));
  }, [activeRun, nodeTypeById]);

  React.useEffect(() => {
    if (
      !selectedObjectRef ||
      selectedObjectRef.owner_pack !== 'ig' ||
      selectedObjectRef.object_kind !== 'discovery_target'
    ) {
      return;
    }
    const graphNodes = toGraphNodes(nodes);
    if (graphNodes.some((node) => node.type === 'object_reference' && (node.payload.ref as AddressableObjectRef | undefined)?.uri === selectedObjectRef.uri)) {
      return;
    }
    const nodeType = nodeTypeById.get('object_reference');
    if (!nodeType) {
      return;
    }
    const nextNode: CompositionGraphNode = {
      id: `object_reference_${Date.now().toString(36)}_${graphNodes.length + 1}`,
      type: 'object_reference',
      position: { x: 80, y: 120 + graphNodes.length * 28 },
      payload: {
        ref: {
          ...selectedObjectRef,
          workspace_id: selectedObjectRef.workspace_id || workspaceId,
        },
      },
      capability_code: null,
      metadata: { pasted_from: 'discovery_targets' },
    };
    applySnapshot({ nodes: [nextNode, ...graphNodes], edges: toGraphEdges(edges) });
    setSelectedNodeId(nextNode.id);
  }, [selectedObjectRef?.uri, selectedObjectRef, workspaceId, nodeTypeById, nodes, edges]);

  function applySnapshot(snapshot: { nodes: CompositionGraphNode[]; edges: CompositionGraphEdge[] }, pushHistory = true) {
    const nextNodes = toFlowNodes(snapshot.nodes, nodeTypeById, activeRun);
    const nextEdges = toFlowEdges(snapshot.edges);
    setNodes(nextNodes);
    setEdges(nextEdges);
    if (pushHistory) {
      setHistory((current) => pushDirectorGraphHistory(current, createDirectorGraphSnapshot(snapshot.nodes, snapshot.edges)));
    }
  }

  function addNode(nodeType: CompositionGraphNodeType, position?: { x: number; y: number }) {
    const graphNodes = toGraphNodes(nodes);
    const graphEdges = toGraphEdges(edges);
    const id = `${nodeType.id}_${Date.now().toString(36)}_${graphNodes.length + 1}`;
    const graphNode: CompositionGraphNode = {
      id,
      type: nodeType.id,
      position: position || { x: 120 + graphNodes.length * 36, y: 120 + graphNodes.length * 28 },
      payload: buildDefaultPayload(nodeType, id, workspaceId),
      capability_code: nodeType.capability_code || null,
      metadata: {},
    };
    applySnapshot({ nodes: [...graphNodes, graphNode], edges: graphEdges });
    setSelectedNodeId(id);
  }

  function canConnect(connection: Connection): boolean {
    const sourceNode = nodes.find((node) => node.id === connection.source);
    const targetNode = nodes.find((node) => node.id === connection.target);
    if (!sourceNode || !targetNode) {
      return false;
    }
    const sourcePort = nodeTypePorts(sourceNode.data.nodeType, 'output').find((port) => port.id === connection.sourceHandle);
    const targetPort = nodeTypePorts(targetNode.data.nodeType, 'input').find((port) => port.id === connection.targetHandle);
    if (!sourcePort || !targetPort) {
      return false;
    }
    return dataTypesCompatible(sourcePort.data_type, targetPort.data_type);
  }

  function handleConnect(connection: Connection) {
    if (!connection.source || !connection.target || !connection.sourceHandle || !connection.targetHandle || !canConnect(connection)) {
      setOperationError(t('directorGraphInvalidConnection'));
      return;
    }
    const graphNodes = toGraphNodes(nodes);
    const graphEdges = toGraphEdges(edges);
    const graphEdge: CompositionGraphEdge = {
      id: `edge_${Date.now().toString(36)}_${graphEdges.length + 1}`,
      source: connection.source,
      target: connection.target,
      source_port: connection.sourceHandle,
      target_port: connection.targetHandle,
      type: defaultEdgeType,
      metadata: {},
    };
    applySnapshot({ nodes: graphNodes, edges: [...graphEdges, graphEdge] });
    setOperationError(null);
  }

  function handleUndo() {
    setHistory((current) => {
      const next = undoDirectorGraphHistory(current);
      applySnapshot(currentDirectorGraphSnapshot(next), false);
      return next;
    });
  }

  function handleRedo() {
    setHistory((current) => {
      const next = redoDirectorGraphHistory(current);
      applySnapshot(currentDirectorGraphSnapshot(next), false);
      return next;
    });
  }

  function handleDelete() {
    if (!selectedNodeId) {
      return;
    }
    const graphNodes = toGraphNodes(nodes).filter((node) => node.id !== selectedNodeId);
    const graphEdges = toGraphEdges(edges).filter((edge) => edge.source !== selectedNodeId && edge.target !== selectedNodeId);
    applySnapshot({ nodes: graphNodes, edges: graphEdges });
    setSelectedNodeId(null);
  }

  function handlePaste() {
    if (!clipboardNode) {
      return;
    }
    const graphNodes = toGraphNodes(nodes);
    const graphEdges = toGraphEdges(edges);
    const id = `${clipboardNode.type}_${Date.now().toString(36)}_${graphNodes.length + 1}`;
    applySnapshot({
      nodes: [
        ...graphNodes,
        {
          ...clipboardNode,
          id,
          position: { x: clipboardNode.position.x + 40, y: clipboardNode.position.y + 40 },
          payload: { ...clipboardNode.payload },
        },
      ],
      edges: graphEdges,
    });
    setSelectedNodeId(id);
  }

  async function handleSave() {
    if (!meetingId) {
      return;
    }
    await saveDraft({
      title: t('directorGraphDraftTitle'),
      meeting_id: meetingId,
      thread_id: threadId || meetingId,
      selected_primary_pack: selectedPrimaryPack,
      nodes: toGraphNodes(nodes),
      edges: toGraphEdges(edges),
      viewport: INITIAL_VIEWPORT,
      metadata: { source_surface: 'meeting_workbench_director_graph' },
    });
  }

  async function handleRun() {
    if (!meetingId) {
      return;
    }
    setRunStatus('running');
    setRunDiagnostics([]);
    try {
      const response = await runCompositionGraph(apiUrl, workspaceId, {
        draft_id: draft?.id,
        graph_id: draft?.graph_id || 'composition_graph_inline',
        meeting_id: meetingId,
        thread_id: threadId || meetingId,
        command: command.trim() || t('directorGraphDefaultCommand'),
        nodes: toGraphNodes(nodes),
        edges: toGraphEdges(edges),
        viewport: INITIAL_VIEWPORT,
        metadata: { source_surface: 'meeting_workbench_director_graph' },
      });
      setActiveRun(response.run);
      setRunStatus(response.run.status);
      setRunDiagnostics(response.run.diagnostics || []);
      let currentRun = response.run;
      while (currentRun.status === 'pending' || currentRun.status === 'running') {
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
        const polled = await fetchCompositionGraphRun(apiUrl, workspaceId, currentRun.id);
        currentRun = polled.run;
        setActiveRun(currentRun);
        setRunStatus(currentRun.status);
        setRunDiagnostics([
          ...(currentRun.diagnostics || []),
          ...Object.values(currentRun.node_states || {}).flatMap((state) => state.diagnostics || []),
        ]);
      }
    } catch (cause) {
      setRunStatus('failed');
      setRunDiagnostics([
        {
          code: 'graph_run_request_failed',
          message: cause instanceof Error ? cause.message : 'Failed to run composition graph.',
          severity: 'error',
        },
      ]);
    }
  }

  function handleExport() {
    const payload = portablePayload({
      graphId: draft?.graph_id || 'composition_graph_inline',
      selectedPrimaryPack,
      nodes: toGraphNodes(nodes),
      edges: toGraphEdges(edges),
    });
    setJsonText(JSON.stringify(payload, null, 2));
    setImportError(null);
  }

  async function handleImport(payload: CompositionGraphImportExportPayload) {
    setImportError(null);
    try {
      const response = await importCompositionGraph(apiUrl, workspaceId, payload, {
        meetingId,
        threadId: threadId || meetingId,
        persist: false,
      });
      if (!response.valid) {
        setImportError(diagnosticText(response.diagnostics || []));
        return;
      }
      setSelectedPrimaryPack(payload.selected_primary_pack || null);
      applySnapshot({ nodes: payload.nodes || [], edges: payload.edges || [] });
    } catch (cause) {
      setImportError(cause instanceof Error ? cause.message : 'Failed to import composition graph.');
    }
  }

  function handleApplyPayload() {
    if (!selectedNodeId) {
      return;
    }
    try {
      const payload = JSON.parse(payloadText);
      if (!isRecord(payload)) {
        throw new Error('Payload must be an object.');
      }
      const graphNodes = toGraphNodes(nodes).map((node) =>
        node.id === selectedNodeId ? { ...node, payload } : node,
      );
      applySnapshot({ nodes: graphNodes, edges: toGraphEdges(edges) });
      setPayloadError(null);
    } catch (cause) {
      setPayloadError(cause instanceof Error ? cause.message : 'Invalid JSON payload.');
    }
  }

  const hasComfyLaneNode = nodes.some((node) => node.data.graphNode.type === 'comfyui_lane_adapter');
  const missingComfyWorkflow = nodes.some((node) => {
    if (node.data.graphNode.type !== 'comfyui_lane_adapter') {
      return false;
    }
    const workflowRef = node.data.graphNode.payload.workflow_ref;
    return typeof workflowRef !== 'string' || workflowRef.trim().length === 0;
  });
  const runBlockedDiagnostics =
    hasComfyLaneNode && comfyLaneOptions.length === 0
      ? comfyLaneDiagnostics
      : missingComfyWorkflow
        ? [
            {
              code: 'comfyui_ready_lane_not_found',
              message: t('directorGraphNoReadyComfyLane'),
              severity: 'error' as const,
            },
          ]
        : [];

  const toolbarButtonClass =
    'inline-flex h-8 w-8 items-center justify-center rounded-md border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-300 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-900 dark:disabled:text-slate-700';

  return (
    <section
      className="flex min-h-0 flex-1 bg-slate-100 text-slate-900 dark:bg-slate-950 dark:text-slate-100"
      data-testid="director-graph-canvas"
    >
      <DirectorGraphPalette
        contracts={contracts}
        nodeTypes={availableNodeTypes}
        selectedPrimaryPack={selectedPrimaryPack}
        onSelectPrimaryPack={setSelectedPrimaryPack}
        onAddNode={addNode}
        t={t}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white px-3 dark:border-slate-800 dark:bg-slate-950">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
              {t('meetingWorkbenchDirectorGraph')}
            </div>
            <div className="truncate text-xs text-slate-500 dark:text-slate-400">
              {contractsLoading
                ? t('directorGraphLoadingContracts')
                : contractsError || diagnosticText(diagnostics) || t('directorGraphReady')}
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button type="button" onClick={handleUndo} className={toolbarButtonClass} data-testid="director-graph-undo" title={t('directorGraphUndo')}>
              <Undo2 className="h-4 w-4" aria-hidden="true" />
            </button>
            <button type="button" onClick={handleRedo} className={toolbarButtonClass} data-testid="director-graph-redo" title={t('directorGraphRedo')}>
              <Redo2 className="h-4 w-4" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={() => selectedNode && setClipboardNode(selectedNode)}
              disabled={!selectedNode}
              className={toolbarButtonClass}
              data-testid="director-graph-copy"
              title={t('directorGraphCopy')}
            >
              <Copy className="h-4 w-4" aria-hidden="true" />
            </button>
            <button type="button" onClick={handlePaste} disabled={!clipboardNode} className={toolbarButtonClass} data-testid="director-graph-paste" title={t('directorGraphPaste')}>
              <Copy className="h-4 w-4 rotate-180" aria-hidden="true" />
            </button>
            <button type="button" onClick={handleDelete} disabled={!selectedNode} className={toolbarButtonClass} data-testid="director-graph-delete" title={t('directorGraphDelete')}>
              <Trash2 className="h-4 w-4" aria-hidden="true" />
            </button>
            <button type="button" onClick={() => window.dispatchEvent(new Event('resize'))} className={toolbarButtonClass} data-testid="director-graph-fit" title={t('directorGraphFit')}>
              <Maximize2 className="h-4 w-4" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={!meetingId || saving}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-slate-200 px-2.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-300 dark:border-slate-800 dark:text-slate-200 dark:hover:bg-slate-900 dark:disabled:text-slate-700"
              data-testid="director-graph-save"
              title={t('directorGraphSave')}
            >
              <Save className="h-4 w-4" aria-hidden="true" />
              <span>{saving ? t('directorGraphSaving') : t('directorGraphSave')}</span>
            </button>
            <DirectorGraphCompileButton
              disabled={!meetingId || runBlockedDiagnostics.length > 0}
              status={runStatus}
              onCompile={handleRun}
              t={t}
            />
          </div>
        </div>
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
                changes.reduce((nextNodes, change) => {
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
        <DirectorGraphImportExport
          value={jsonText}
          error={importError}
          onChange={setJsonText}
          onExport={handleExport}
          onImport={handleImport}
          onInvalidImport={setImportError}
          t={t}
        />
        {operationError || saveError || runBlockedDiagnostics.length > 0 || runDiagnostics.length > 0 ? (
          <div className="border-t border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200" data-testid="director-graph-diagnostics">
            {operationError || saveError || diagnosticText(runBlockedDiagnostics) || diagnosticText(runDiagnostics)}
          </div>
        ) : null}
      </div>
      <DirectorGraphInspector
        node={selectedNode}
        nodeType={selectedNodeType}
        payloadText={payloadText}
        error={payloadError}
        comfyLaneOptions={comfyLaneOptions}
        onPayloadTextChange={setPayloadText}
        onApplyPayload={handleApplyPayload}
        onPatchPayload={(patch) => {
          if (!selectedNodeId) {
            return;
          }
          const graphNodes = toGraphNodes(nodes).map((node) =>
            node.id === selectedNodeId ? { ...node, payload: { ...node.payload, ...patch } } : node,
          );
          applySnapshot({ nodes: graphNodes, edges: toGraphEdges(edges) });
        }}
        t={t}
      />
    </section>
  );
}
