import type { Dispatch, SetStateAction } from 'react';
import type { Connection } from '@xyflow/react';

import type {
  CompositionGraphContract,
  CompositionGraphDiagnostic,
  CompositionGraphImportExportPayload,
  CompositionGraphNode,
  CompositionGraphNodeOption,
  CompositionGraphNodeType,
  CompositionGraphRunStatus,
} from '@/lib/composition-graph';
import type { MeetingWorkbenchViewportClass } from '../meetingWorkbenchPanelLayoutState';
import type { MeetingTranslate } from '../meetingWorkbenchTypes';
import {
  DirectorGraphCompactPrimaryActions,
  DirectorGraphCompactUtilityActions,
  DirectorGraphDesktopToolbar,
} from './DirectorGraphCanvasActions';
import { diagnosticText, getUnknownNodeType, type DirectorGraphFlowEdge, type DirectorGraphFlowNode } from './DirectorGraphCanvasModel';
import { DirectorGraphFlowSurface } from './DirectorGraphFlowSurface';
import { DirectorGraphImportExport } from './DirectorGraphImportExport';
import { DirectorGraphInspector } from './DirectorGraphInspector';
import { DirectorGraphPalette } from './DirectorGraphPalette';
import { DirectorGraphResponsiveSurface, type DirectorGraphSecondarySurface } from './DirectorGraphResponsiveSurface';
import { nodeTypes } from './DirectorGraphNodeView';

type DirectorGraphCanvasShellProps = {
  viewportClass: MeetingWorkbenchViewportClass;
  contracts: CompositionGraphContract[];
  contractsLoading: boolean;
  contractsError: string | null;
  diagnostics: CompositionGraphDiagnostic[];
  availableNodeTypes: CompositionGraphNodeType[];
  selectedPrimaryPack: string | null;
  onSelectPrimaryPack: (pack: string | null) => void;
  selectedNode: CompositionGraphNode | null;
  payloadText: string;
  payloadError: string | null;
  comfyLaneOptions: CompositionGraphNodeOption[];
  jsonText: string;
  importError: string | null;
  nodes: DirectorGraphFlowNode[];
  edges: DirectorGraphFlowEdge[];
  nodeTypeById: Map<string, CompositionGraphNodeType>;
  selectedNodeId: string | null;
  setNodes: Dispatch<SetStateAction<DirectorGraphFlowNode[]>>;
  setSelectedNodeId: (nodeId: string | null) => void;
  compactSurface: DirectorGraphSecondarySurface | null;
  canPaste: boolean;
  meetingId: string | null;
  saving: boolean;
  runStatus: CompositionGraphRunStatus | 'idle';
  operationError: string | null;
  saveError: string | null;
  runDiagnostics: CompositionGraphDiagnostic[];
  comfyLaneDiagnostics: CompositionGraphDiagnostic[];
  addNode: (nodeType: CompositionGraphNodeType, position?: { x: number; y: number }) => void;
  handleConnect: (connection: Connection) => void;
  handleUndo: () => void;
  handleRedo: () => void;
  handleCopySelectedNode: () => void;
  handlePaste: () => void;
  handleDelete: () => void;
  handleSave: () => void;
  handleRun: () => void;
  handleToggleCompactSurface: (surface: DirectorGraphSecondarySurface) => void;
  handleApplyPayload: () => void;
  handlePatchSelectedNode: (patch: Record<string, unknown>) => void;
  handleExport: () => void;
  handleImport: (payload: CompositionGraphImportExportPayload) => void;
  setPayloadText: (value: string) => void;
  setJsonText: (value: string) => void;
  setImportError: (message: string) => void;
  closeCompactSurface: () => void;
  t: MeetingTranslate;
};

export function DirectorGraphCanvasShell({
  viewportClass,
  contracts,
  contractsLoading,
  contractsError,
  diagnostics,
  availableNodeTypes,
  selectedPrimaryPack,
  onSelectPrimaryPack,
  selectedNode,
  payloadText,
  payloadError,
  comfyLaneOptions,
  jsonText,
  importError,
  nodes,
  edges,
  nodeTypeById,
  selectedNodeId,
  setNodes,
  setSelectedNodeId,
  compactSurface,
  canPaste,
  meetingId,
  saving,
  runStatus,
  operationError,
  saveError,
  runDiagnostics,
  comfyLaneDiagnostics,
  addNode,
  handleConnect,
  handleUndo,
  handleRedo,
  handleCopySelectedNode,
  handlePaste,
  handleDelete,
  handleSave,
  handleRun,
  handleToggleCompactSurface,
  handleApplyPayload,
  handlePatchSelectedNode,
  handleExport,
  handleImport,
  setPayloadText,
  setJsonText,
  setImportError,
  closeCompactSurface,
  t,
}: DirectorGraphCanvasShellProps) {
  const compactViewport = viewportClass !== 'desktop';
  const mobileViewport = viewportClass === 'mobile';
  const selectedNodeType = selectedNode ? nodeTypeById.get(selectedNode.type) || getUnknownNodeType(selectedNode.type) : null;
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
        ? [{ code: 'comfyui_ready_lane_not_found', message: t('directorGraphNoReadyComfyLane'), severity: 'error' as const }]
        : [];
  const statusText = contractsLoading
    ? t('directorGraphLoadingContracts')
    : contractsError || diagnosticText(diagnostics) || t('directorGraphReady');
  const diagnosticsText =
    operationError || saveError || diagnosticText(runBlockedDiagnostics) || diagnosticText(runDiagnostics);
  const saveButtonLabel = saving ? t('directorGraphSaving') : t('directorGraphSave');
  const runDisabled = !meetingId || runBlockedDiagnostics.length > 0;

  const palettePanel = (
    <DirectorGraphPalette
      contracts={contracts}
      nodeTypes={availableNodeTypes}
      selectedPrimaryPack={selectedPrimaryPack}
      onSelectPrimaryPack={onSelectPrimaryPack}
      onAddNode={addNode}
      presentation={compactViewport ? 'drawer' : 'inline'}
      t={t}
    />
  );
  const inspectorPanel = (
    <DirectorGraphInspector
      node={selectedNode}
      nodeType={selectedNodeType}
      payloadText={payloadText}
      error={payloadError}
      comfyLaneOptions={comfyLaneOptions}
      onPayloadTextChange={setPayloadText}
      onApplyPayload={handleApplyPayload}
      onPatchPayload={handlePatchSelectedNode}
      presentation={compactViewport ? 'drawer' : 'inline'}
      t={t}
    />
  );
  const importExportPanel = (
    <DirectorGraphImportExport
      value={jsonText}
      error={importError}
      onChange={setJsonText}
      onExport={handleExport}
      onImport={handleImport}
      onInvalidImport={setImportError}
      presentation={compactViewport ? 'drawer' : 'inline'}
      t={t}
    />
  );
  const diagnosticsNode = diagnosticsText ? (
    <div
      className="border-t border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200"
      data-testid="director-graph-diagnostics"
    >
      {diagnosticsText}
    </div>
  ) : null;

  return (
    <DirectorGraphResponsiveSurface
      viewportClass={viewportClass}
      title={t('meetingWorkbenchDirectorGraph')}
      status={statusText}
      palette={palettePanel}
      canvas={
        <DirectorGraphFlowSurface
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          nodeTypeById={nodeTypeById}
          selectedNodeId={selectedNodeId}
          setNodes={setNodes}
          setSelectedNodeId={setSelectedNodeId}
          addNode={addNode}
          handleConnect={handleConnect}
        />
      }
      inspector={inspectorPanel}
      importExport={importExportPanel}
      diagnostics={diagnosticsNode}
      desktopToolbar={
        <DirectorGraphDesktopToolbar
          canCopy={Boolean(selectedNode)}
          canPaste={canPaste}
          canDelete={Boolean(selectedNode)}
          meetingId={meetingId}
          saving={saving}
          saveButtonLabel={saveButtonLabel}
          runDisabled={runDisabled}
          runStatus={runStatus}
          onUndo={handleUndo}
          onRedo={handleRedo}
          onCopy={handleCopySelectedNode}
          onPaste={handlePaste}
          onDelete={handleDelete}
          onSave={handleSave}
          onRun={handleRun}
          t={t}
        />
      }
      compactPrimaryActions={
        <DirectorGraphCompactPrimaryActions
          meetingId={meetingId}
          saving={saving}
          saveButtonLabel={saveButtonLabel}
          runDisabled={runDisabled}
          runStatus={runStatus}
          onSave={handleSave}
          onRun={handleRun}
          mobileViewport={mobileViewport}
          t={t}
        />
      }
      compactUtilityActions={
        <DirectorGraphCompactUtilityActions
          canCopy={Boolean(selectedNode)}
          canPaste={canPaste}
          canDelete={Boolean(selectedNode)}
          compactSurface={compactSurface}
          onToggleCompactSurface={handleToggleCompactSurface}
          onUndo={handleUndo}
          onRedo={handleRedo}
          onCopy={handleCopySelectedNode}
          onPaste={handlePaste}
          onDelete={handleDelete}
          t={t}
        />
      }
      compactSurface={compactSurface}
      onCloseCompactSurface={closeCompactSurface}
      t={t}
    />
  );
}
