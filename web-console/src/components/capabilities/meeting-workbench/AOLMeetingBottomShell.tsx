'use client';

import React, { useEffect, useMemo, useState } from 'react';

import type { AddressableObjectRole } from '@/lib/addressable-object-layer';
import type { CompositionGraphCommandEnvelopeDraft } from '@/lib/composition-graph';
import { useT } from '@/lib/i18n';
import { CANVAS_ZOOM_STEP } from './meetingWorkbenchConstants';
import { getMentionQuery } from './meetingMentions';
import { buildCommandImpact, projectMeetingGraph } from './meetingGraphProjection';
import { createMeetingCommandSubmitHandler, submitCompiledCompositionGraphCommand } from './meetingCommandSubmit';
import { dispatchMeetingCommandLedgerUpdated } from './meetingCommandEvents';
import { dispatchMeetingSessionNotification } from './meetingSessionNotifications';
import { applyGuidanceCommandDraft } from './meetingGuidanceCommand';
import { clampCanvasZoom, MeetingHeaderToolbar } from './SemanticFlowCanvas';
import { MeetingWorkbenchStage } from './MeetingWorkbenchStage';
import { MeetingCommandBar } from './CommandDock';
import { MeetingConsoleDrawer, MeetingInspectorPanel, MeetingInspectorRail } from './PropertiesInspector';
import { MeetingSessionNotification } from './MeetingSessionNotification';
import { MeetingObjectContextPanel, MeetingSessionsPopover } from './MeetingContextPanels';
import { useMeetingWorkbenchData } from './useMeetingWorkbenchData';
import { useMeetingMentionItems } from './useMeetingMentionItems';
import { useMeetingSessionNotification } from './useMeetingSessionNotification';
import {
  getMeetingFocusRole,
  getMeetingMissingContext,
  getMeetingNextStepNodeId,
  getMeetingNextStepTitle,
  getMeetingRuntimeLabel,
  getMeetingWorkStatus,
  type MeetingMissingContext,
} from './meetingWorkbenchStatus';
import type {
  AOLMeetingBottomShellProps,
  GraphViewMode,
  InspectorTab,
  MeetingInfoPanel,
  MeetingMentionItem,
  MeetingNode,
  MeetingTranslate,
} from './meetingWorkbenchTypes';

function getMeetingRoleLabel(role: AddressableObjectRole | null, t: MeetingTranslate): string | null {
  if (role === 'target') {
    return t('meetingWorkbenchRoleTarget');
  }
  if (role === 'evidence') {
    return t('meetingWorkbenchRoleEvidence');
  }
  if (role === 'constraint') {
    return t('meetingWorkbenchRoleConstraint');
  }
  if (role === 'baseline') {
    return t('meetingWorkbenchRoleBaseline');
  }
  if (role === 'source') {
    return t('meetingWorkbenchRoleSource');
  }
  return null;
}

function getMissingContextLabel(context: MeetingMissingContext | null, t: MeetingTranslate): string | null {
  if (context === 'target') {
    return t('meetingWorkbenchRoleTarget');
  }
  return null;
}

export function AOLMeetingBottomShell({
  workspaceId,
  apiUrl,
  capabilityCode = 'ig',
  meetingId,
  summary,
  selection,
  attachResponse,
  surfaceRoute,
  onSwitchObject,
}: AOLMeetingBottomShellProps) {
  const t = useT();
  const [selectedNodeId, setSelectedNodeId] = useState('ready');
  const [activeInspector, setActiveInspector] = useState<InspectorTab | null>(null);
  const [activeInfoPanel, setActiveInfoPanel] = useState<MeetingInfoPanel | null>(null);
  const [graphViewMode, setGraphViewMode] = useState<GraphViewMode>('work');
  const [activeTraceFilter, setActiveTraceFilter] = useState<string | null>(null);
  const [isConsoleOpen, setIsConsoleOpen] = useState(false);
  const [command, setCommand] = useState('');
  const [localTasks, setLocalTasks] = useState<MeetingNode[]>([]);
  const [dispatchError, setDispatchError] = useState<string | null>(null);
  const [canvasZoom, setCanvasZoom] = useState(1);
  const [selectedPackToolId, setSelectedPackToolId] = useState('auto');
  const [appliedMentionItems, setAppliedMentionItems] = useState<MeetingMentionItem[]>([]);
  const [isDispatching, setIsDispatching] = useState(false);
  const [activeMissingContext, setActiveMissingContext] = useState<MeetingMissingContext | null>(null);
  const activeMentionQuery = getMentionQuery(command);
  const {
    activeMeetingId,
    setActiveMeetingId,
    startBlankMeetingSession,
    startingBlankMeetingSession,
    startBlankMeetingSessionError,
    meetingSessions,
    meetingSessionsLoading,
    meetingSessionsError,
    meetingEvents,
    meetingEventsLoading,
    meetingEventsError,
    executionGraphNodes,
    executionGraphEdges,
    executionGraphLoading,
    executionGraphError,
    objectGraphProjections,
    objectGraphNodes,
    objectGraphLoading,
    objectGraphError,
    meetingArtifacts,
    meetingArtifactsLoading,
    meetingArtifactsError,
    packTools,
    packToolsLoading,
    packToolsError,
    registryMentionItems,
    registryMentionItemsLoading,
    registryMentionItemsError,
    runtimeSnapshot,
    effectiveSummary,
    effectiveSelection,
    effectiveAttachResponse,
    objectTitle,
    objectKind,
    hasObjectContext,
  } = useMeetingWorkbenchData({
    workspaceId,
    apiUrl,
    meetingId,
    summary,
    selection,
    attachResponse,
    activeMentionQuery,
    activeInspector,
  });
  useEffect(() => {
    setLocalTasks([]);
    setActiveTraceFilter(null);
    setAppliedMentionItems([]);
    setActiveMissingContext(null);
  }, [activeMeetingId]);
  const { sessionNotification, clearSessionNotification } = useMeetingSessionNotification({
    workspaceId,
    activeMeetingId,
  });

  const graphProjection = useMemo(
    () => projectMeetingGraph({
      activeMeetingId,
      objectKind,
      objectTitle,
      objectDetail: effectiveSummary?.summary_text || 'Owner-backed object context is attached.',
      events: meetingEvents,
      artifacts: meetingArtifacts,
      localTasks,
      objectGraphNodes,
      artifactsLoading: meetingArtifactsLoading,
      artifactsError: meetingArtifactsError,
      eventsLoading: meetingEventsLoading,
      eventsError: meetingEventsError,
      executionGraphNodes,
      executionGraphEdges,
      executionGraphLoading,
      executionGraphError,
      mode: graphViewMode,
    }),
    [
      activeMeetingId,
      effectiveSummary?.summary_text,
      executionGraphEdges,
      executionGraphError,
      executionGraphLoading,
      executionGraphNodes,
      graphViewMode,
      localTasks,
      meetingArtifacts,
      meetingArtifactsError,
      meetingArtifactsLoading,
      meetingEvents,
      meetingEventsError,
      meetingEventsLoading,
      objectGraphNodes,
      objectKind,
      objectTitle,
    ],
  );
  const nodes = graphProjection.nodes;
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? nodes[0] ?? null;
  const activeWorkStatus = useMemo(() => getMeetingWorkStatus(nodes, command), [command, nodes]);
  const nextStepTitle = useMemo(() => getMeetingNextStepTitle(nodes), [nodes]);
  const nextStepNodeId = useMemo(() => getMeetingNextStepNodeId(nodes), [nodes]);
  const runtimeLabel = useMemo(() => getMeetingRuntimeLabel(runtimeSnapshot), [runtimeSnapshot]);
  const missingContext = useMemo(
    () => hasObjectContext ? getMeetingMissingContext(nodes, effectiveAttachResponse) : null,
    [effectiveAttachResponse, hasObjectContext, nodes],
  );
  const focusRoleLabel = useMemo(
    () => getMeetingRoleLabel(getMeetingFocusRole(effectiveSummary, effectiveAttachResponse), t),
    [effectiveAttachResponse, effectiveSummary, t],
  );
  const missingContextLabel = useMemo(
    () => getMissingContextLabel(missingContext, t),
    [missingContext, t],
  );
  const selectedCommandImpact = useMemo(
    () => buildCommandImpact(selectedNode, nodes, graphProjection.edges, graphProjection.traceEvents),
    [graphProjection.edges, graphProjection.traceEvents, nodes, selectedNode],
  );
  const mentionItems = useMeetingMentionItems({
    activeMeetingId,
    appliedMentionItems,
    effectiveSummary,
    nodes,
    objectTitle,
    packTools,
    registryMentionItems,
  });

  function handleToggleInfoPanel(panel: MeetingInfoPanel) {
    setActiveInfoPanel((current) => (current === panel ? null : panel));
  }

  async function handleStartBlankMeetingSession() {
    try {
      const session = await startBlankMeetingSession({
        active_capability_code: capabilityCode,
        active_pack_code: capabilityCode,
        source_surface: surfaceRoute || 'meeting_workbench',
      });
      setSelectedNodeId('ready');
      setIsConsoleOpen(false);
      setActiveInfoPanel(null);
      dispatchMeetingSessionNotification({
        workspaceId,
        meetingId: session.id,
        tone: 'info',
        title: t('meetingWorkbenchNotificationCommandAccepted'),
        message: 'Blank meeting session is ready.',
      });
    } catch (error) {
      setDispatchError(error instanceof Error ? error.message : 'Failed to start meeting session.');
    }
  }

  function handleCanvasZoom(delta: number) {
    setCanvasZoom((current) => clampCanvasZoom(current + delta));
  }

  function handleCanvasWheelZoom(deltaY: number) {
    const delta = deltaY < 0 ? CANVAS_ZOOM_STEP : -CANVAS_ZOOM_STEP;
    handleCanvasZoom(delta);
  }

  function handleApplyMention(item: MeetingMentionItem) {
    if (!item.ref && !item.packToolId) {
      return;
    }

    setAppliedMentionItems((current) => {
      const next = current.filter((candidate) => candidate.token !== item.token);
      next.push(item);
      return next.slice(-24);
    });
  }

  function handleToggleInspector(tab: InspectorTab) {
    setActiveInspector((current) => (current === tab ? null : tab));
  }

  function handleGraphViewModeChange(mode: GraphViewMode) {
    setGraphViewMode(mode);
    if (mode === 'trace') {
      setActiveInspector('trace');
    }
  }

  function handleSelectNode(nodeId: string) {
    const node = nodes.find((candidate) => candidate.id === nodeId) ?? null;
    setActiveMissingContext(null);
    setSelectedNodeId(nodeId);
    applyGuidanceCommandDraft({
      node,
      packTools,
      currentCommand: command,
      onCommandDraft: setCommand,
      onPackToolSelect: setSelectedPackToolId,
    });
    if (node?.traceFilter) {
      setActiveTraceFilter(node.traceFilter);
    }
    if (node?.kind === 'command') {
      setActiveInspector('trace');
      return;
    }
    if (node?.defaultInspector) {
      setActiveInspector(node.defaultInspector);
    }
  }

  function handleSelectNextStep() {
    if (!nextStepNodeId) {
      return;
    }
    handleSelectNode(nextStepNodeId);
  }

  function handleSelectMissingContext(context: MeetingMissingContext) {
    setActiveMissingContext(context);
    setSelectedNodeId('ready');
    if (!command.trim()) {
      setCommand('@');
    }
  }

  async function handleCompiledGraphEnvelope(envelope: CompositionGraphCommandEnvelopeDraft) {
    if (!activeMeetingId) {
      return;
    }
    const nextNodeId = `task-${localTasks.length + 1}`;
    setLocalTasks((current) => [
      ...current,
      {
        id: nextNodeId,
        eyebrow: 'Composition Graph',
        title: envelope.intent_text,
        detail: t('directorGraphDispatching'),
        status: 'running',
        kind: 'run',
        lane: 'runs',
      },
    ]);
    setSelectedNodeId(nextNodeId);
    setDispatchError(null);
    setIsConsoleOpen(true);
    setIsDispatching(true);
    try {
      const commandLedger = await submitCompiledCompositionGraphCommand({
        apiUrl,
        workspaceId,
        meetingId: activeMeetingId,
        envelope,
      });
      dispatchMeetingCommandLedgerUpdated({
        workspaceId,
        meetingId: activeMeetingId,
        commandId: commandLedger.commandId,
        status: commandLedger.status,
      });
      dispatchMeetingSessionNotification({
        workspaceId,
        meetingId: activeMeetingId,
        commandId: commandLedger.commandId,
        tone: commandLedger.status === 'failed' ? 'error' : 'info',
        title: commandLedger.status === 'failed'
          ? t('meetingWorkbenchNotificationCommandFailed')
          : t('meetingWorkbenchNotificationCommandAccepted'),
        message: t('meetingWorkbenchNotificationAwaitingRuntime'),
      });
      setLocalTasks((current) =>
        current.map((node) =>
          node.id === nextNodeId
            ? {
                ...node,
                detail: t('meetingWorkbenchNotificationCommandAccepted'),
                status: commandLedger.status === 'failed' ? 'error' : 'ready',
                output: commandLedger.commandId,
              }
            : node,
        ),
      );
      setCommand('');
    } catch (cause) {
      const errorMessage = cause instanceof Error ? cause.message : 'Failed to dispatch compiled composition graph.';
      setDispatchError(errorMessage);
      setLocalTasks((current) =>
        current.map((node) =>
          node.id === nextNodeId
            ? {
                ...node,
                detail: errorMessage,
                status: 'error',
                output: errorMessage,
              }
            : node,
        ),
      );
    } finally {
      setIsDispatching(false);
    }
  }

  const handleSubmitCommand = createMeetingCommandSubmitHandler({
    command,
    activeMeetingId,
    mentionItems,
    packTools,
    selectedPackToolId,
    effectiveSummary,
    effectiveSelection,
    selectedNode,
    objectTitle,
    activeCapabilityCode: capabilityCode,
    localTaskCount: localTasks.length,
    apiUrl,
    workspaceId,
    setIsDispatching,
    setLocalTasks,
    setSelectedNodeId,
    setCommand,
    setIsConsoleOpen,
    setDispatchError,
    t,
  });

  return (
    <div
      className="flex h-full min-h-0 bg-slate-100 text-slate-900 dark:bg-slate-950 dark:text-slate-100"
      data-testid="aol-meeting-bottom-shell"
    >
      <div className="flex min-w-0 flex-1 flex-col">
        <MeetingHeaderToolbar
          activePanel={activeInfoPanel}
          activeMeetingId={activeMeetingId}
          sessionsCount={meetingSessions.length}
          sessionsLoading={meetingSessionsLoading}
          objectTitle={objectTitle}
          hasObjectContext={hasObjectContext}
          graphViewMode={graphViewMode}
          primaryCount={graphProjection.primaryCount}
          traceCount={graphProjection.traceCount}
          workStatus={activeWorkStatus}
          nextStepTitle={nextStepTitle}
          runtimeLabel={runtimeLabel}
          focusRoleLabel={focusRoleLabel}
          missingContextLabel={missingContextLabel}
          startingBlankMeetingSession={startingBlankMeetingSession}
          onStartBlankMeetingSession={handleStartBlankMeetingSession}
          onSelectNextStep={nextStepNodeId ? handleSelectNextStep : null}
          onSelectMissingContext={missingContext ? () => handleSelectMissingContext(missingContext) : null}
          onTogglePanel={handleToggleInfoPanel}
          onGraphViewModeChange={handleGraphViewModeChange}
          t={t}
        />
        <div className="relative flex min-h-0 flex-1">
          {activeInfoPanel === 'object' ? (
            <div className="pointer-events-none absolute left-3 top-3 z-30 h-[calc(100%-1.5rem)] w-[min(340px,calc(100%-1.5rem))]">
              <MeetingObjectContextPanel
                summary={effectiveSummary}
                selection={effectiveSelection}
                attachResponse={effectiveAttachResponse}
                meetingId={activeMeetingId}
                surfaceRoute={surfaceRoute}
                onSwitchObject={onSwitchObject}
                onClose={() => setActiveInfoPanel(null)}
              />
            </div>
          ) : null}
          {activeInfoPanel === 'sessions' ? (
            <div className="pointer-events-none absolute left-3 right-3 top-3 z-30 md:right-16">
              <MeetingSessionsPopover
                sessions={meetingSessions}
                activeMeetingId={activeMeetingId}
                loading={meetingSessionsLoading}
                error={meetingSessionsError}
                creating={startingBlankMeetingSession}
                createError={startBlankMeetingSessionError}
                onCreateSession={handleStartBlankMeetingSession}
                onSelectSession={(session) => {
                  setActiveMeetingId(session.id);
                  setSelectedNodeId('ready');
                  setIsConsoleOpen(false);
                  setActiveInfoPanel(null);
                }}
                onClose={() => setActiveInfoPanel(null)}
              />
            </div>
          ) : null}
          <MeetingWorkbenchStage
            apiUrl={apiUrl}
            workspaceId={workspaceId}
            meetingId={activeMeetingId}
            graphViewMode={graphViewMode}
            nodes={nodes}
            edges={graphProjection.edges}
            summary={effectiveSummary}
            attachResponse={effectiveAttachResponse}
            selectedNodeId={selectedNodeId}
            activeMissingContext={activeMissingContext}
            onSelectNode={handleSelectNode}
            onSelectMissingContext={handleSelectMissingContext}
            zoom={canvasZoom}
            onZoomIn={() => handleCanvasZoom(CANVAS_ZOOM_STEP)}
            onZoomOut={() => handleCanvasZoom(-CANVAS_ZOOM_STEP)}
            onResetView={() => {
              setCanvasZoom(1);
              setSelectedNodeId('ready');
            }}
            onWheelZoom={handleCanvasWheelZoom}
            commandImpact={selectedCommandImpact}
            command={command}
            selectedPackTool={selectedPackToolId === 'auto' ? null : selectedPackToolId}
            mentionItems={mentionItems}
            selectedObjectRef={effectiveSummary?.ref || null}
            onCommandEnvelope={handleCompiledGraphEnvelope}
            t={t}
            inspectorSlot={
              <>
                <MeetingInspectorRail activeInspector={activeInspector} graphViewMode={graphViewMode} onToggleInspector={handleToggleInspector} t={t} />
                {activeInspector ? (
                  <MeetingInspectorPanel
                    activeInspector={activeInspector}
                    graphViewMode={graphViewMode}
                    selectedNode={selectedNode}
                    runtimeSnapshot={runtimeSnapshot}
                    workspaceId={workspaceId}
                    apiUrl={apiUrl}
                    capabilityCode={capabilityCode}
                    meetingId={activeMeetingId}
                    summary={effectiveSummary}
                    attachResponse={effectiveAttachResponse}
                    surfaceRoute={surfaceRoute}
                    objectGraphProjections={objectGraphProjections}
                    objectGraphLoading={objectGraphLoading}
                    objectGraphError={objectGraphError}
                    commandImpact={selectedCommandImpact}
                    traceEvents={graphProjection.traceEvents}
                    eventCounts={graphProjection.eventCounts}
                    activeTraceFilter={activeTraceFilter}
                    onTraceFilterChange={setActiveTraceFilter}
                    onClose={() => setActiveInspector(null)}
                    t={t}
                  />
                ) : null}
              </>
            }
          />
        </div>
        {isConsoleOpen ? (
          <MeetingConsoleDrawer
            selectedNode={selectedNode}
            onClose={() => {
              setIsConsoleOpen(false);
            }}
          />
        ) : null}
        {sessionNotification ? (
          <MeetingSessionNotification
            notification={sessionNotification}
            dismissLabel={t('meetingWorkbenchDismissNotification')}
            onClose={clearSessionNotification}
          />
        ) : null}
        <MeetingCommandBar
          command={command}
          onCommandChange={setCommand}
          onSubmitCommand={handleSubmitCommand}
          isDispatching={isDispatching}
          isConsoleOpen={isConsoleOpen}
          onToggleConsole={() => {
            setIsConsoleOpen((current) => !current);
          }}
          packTools={packTools}
          selectedPackToolId={selectedPackToolId}
          onSelectedPackToolChange={setSelectedPackToolId}
          packToolsLoading={packToolsLoading}
          packToolsError={packToolsError}
          hasActiveMeeting={Boolean(activeMeetingId)}
          mentionItems={mentionItems}
          mentionItemsLoading={packToolsLoading || registryMentionItemsLoading}
          mentionItemsError={registryMentionItemsError}
          onApplyMention={handleApplyMention}
          missingContextLabel={missingContextLabel}
          t={t}
        />
        {dispatchError ? (
          <div
            className="border-t border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-300"
            data-testid="meeting-dispatch-error"
          >
            {dispatchError}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default AOLMeetingBottomShell;
