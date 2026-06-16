'use client';

import React, { useMemo, useState } from 'react';
import { type Connection } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import {
  fetchCompositionGraphNodeOptions,
  importCompositionGraph,
  runCompositionGraph,
  type CompositionGraphCommandEnvelopeDraft,
  type CompositionGraphDiagnostic,
  type CompositionGraphEdge,
  type CompositionGraphImportExportPayload,
  type CompositionGraphNode,
  type CompositionGraphNodeOption,
  type CompositionGraphRun,
  type CompositionGraphRunStatus,
  type CompositionGraphNodeType,
} from '@/lib/composition-graph';
import type { AddressableObjectRef } from '@/lib/addressable-object-layer';
import { useMeetingWorkbenchViewportClass } from '../meetingWorkbenchPanelLayoutState';
import type { MeetingMentionItem, MeetingTranslate } from '../meetingWorkbenchTypes';
import {
  INITIAL_VIEWPORT,
  buildDefaultPayload,
  dataTypesCompatible,
  diagnosticText,
  isRecord,
  nodeTypePorts,
  portablePayload,
  toFlowEdges,
  toFlowNodes,
  toGraphEdges,
  toGraphNodes,
  type DirectorGraphFlowEdge,
  type DirectorGraphFlowNode,
} from './DirectorGraphCanvasModel';
import { DirectorGraphCanvasShell } from './DirectorGraphCanvasShell';
import {
  createDirectorGraphHistory,
  createDirectorGraphSnapshot,
  currentDirectorGraphSnapshot,
  pushDirectorGraphHistory,
  redoDirectorGraphHistory,
  type DirectorGraphHistoryState,
  undoDirectorGraphHistory,
} from './DirectorGraphHistory';
import type { DirectorGraphSecondarySurface } from './DirectorGraphResponsiveSurface';
import { useCompositionGraphContracts } from './useCompositionGraphContracts';
import { useCompositionGraphDraft } from './useCompositionGraphDraft';
import { useCompositionGraphRunMonitor } from './useCompositionGraphRunMonitor';

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
  const [compactSurface, setCompactSurface] = useState<DirectorGraphSecondarySurface | null>(null);

  const runMonitor = useCompositionGraphRunMonitor({
    apiUrl,
    workspaceId,
    onRun: (run) => {
      setActiveRun(run);
      setRunStatus(run.status);
      setRunDiagnostics([
        ...(run.diagnostics || []),
        ...Object.values(run.node_states || {}).flatMap((state) => state.diagnostics || []),
      ]);
    },
    onError: (error) => {
      setRunStatus('failed');
      setRunDiagnostics([
        {
          code: 'graph_run_monitor_failed',
          message: error.message,
          severity: 'error',
        },
      ]);
    },
  });
  const [comfyLaneOptions, setComfyLaneOptions] = useState<CompositionGraphNodeOption[]>([]);
  const [comfyLaneDiagnostics, setComfyLaneDiagnostics] = useState<CompositionGraphDiagnostic[]>([]);
  const { draft, saveDraft, saveError, saving } = useCompositionGraphDraft({ apiUrl, workspaceId });

  const selectedNode = useMemo(
    () => toGraphNodes(nodes).find((node) => node.id === selectedNodeId) || null,
    [nodes, selectedNodeId],
  );
  const viewportClass = useMeetingWorkbenchViewportClass();

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
    if (viewportClass === 'desktop') {
      setCompactSurface(null);
    }
  }, [viewportClass]);

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
      runMonitor.subscribe(response.run);
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

  function handleToggleCompactSurface(surface: DirectorGraphSecondarySurface) {
    setCompactSurface((current) => (current === surface ? null : surface));
  }

  function handlePatchSelectedNode(patch: Record<string, unknown>) {
    if (!selectedNodeId) {
      return;
    }
    const graphNodes = toGraphNodes(nodes).map((node) =>
      node.id === selectedNodeId ? { ...node, payload: { ...node.payload, ...patch } } : node,
    );
    applySnapshot({ nodes: graphNodes, edges: toGraphEdges(edges) });
  }

  return (
    <DirectorGraphCanvasShell
      viewportClass={viewportClass}
      contracts={contracts}
      contractsLoading={contractsLoading}
      contractsError={contractsError}
      diagnostics={diagnostics}
      availableNodeTypes={availableNodeTypes}
      selectedPrimaryPack={selectedPrimaryPack}
      onSelectPrimaryPack={setSelectedPrimaryPack}
      selectedNode={selectedNode}
      payloadText={payloadText}
      payloadError={payloadError}
      comfyLaneOptions={comfyLaneOptions}
      jsonText={jsonText}
      importError={importError}
      nodes={nodes}
      edges={edges}
      nodeTypeById={nodeTypeById}
      selectedNodeId={selectedNodeId}
      setNodes={setNodes}
      setSelectedNodeId={setSelectedNodeId}
      compactSurface={compactSurface}
      canPaste={Boolean(clipboardNode)}
      meetingId={meetingId}
      saving={saving}
      runStatus={runStatus}
      operationError={operationError}
      saveError={saveError}
      runDiagnostics={runDiagnostics}
      comfyLaneDiagnostics={comfyLaneDiagnostics}
      addNode={addNode}
      handleConnect={handleConnect}
      handleUndo={handleUndo}
      handleRedo={handleRedo}
      handleCopySelectedNode={() => selectedNode && setClipboardNode(selectedNode)}
      handlePaste={handlePaste}
      handleDelete={handleDelete}
      handleSave={handleSave}
      handleRun={handleRun}
      handleToggleCompactSurface={handleToggleCompactSurface}
      handleApplyPayload={handleApplyPayload}
      handlePatchSelectedNode={handlePatchSelectedNode}
      handleExport={handleExport}
      handleImport={handleImport}
      setPayloadText={setPayloadText}
      setJsonText={setJsonText}
      setImportError={setImportError}
      closeCompactSurface={() => setCompactSurface(null)}
      t={t}
    />
  );
}
