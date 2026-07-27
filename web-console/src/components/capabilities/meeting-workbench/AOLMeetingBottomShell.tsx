'use client';
import React, { useEffect } from 'react';
import { useT } from '@/lib/i18n';
import { CANVAS_ZOOM_STEP } from './meetingWorkbenchConstants';
import { getMentionQuery, rememberAppliedMentionItem } from './meetingMentions';
import { createMeetingWorkbenchCommandDispatchHandlers } from './meetingWorkbenchCommandDispatchHandlers';
import { dispatchMeetingSessionNotification } from './meetingSessionNotifications';
import { applyGuidanceCommandDraft } from './meetingGuidanceCommand';
import { clampCanvasZoom } from './SemanticFlowCanvas';
import { MeetingConsoleDrawer } from './PropertiesInspector';
import { MeetingWorkbenchInspectorDock } from './MeetingWorkbenchInspectorDock';
import { MeetingWorkbenchStageLayout } from './MeetingWorkbenchStageLayout';
import { createMeetingWorkbenchSecondarySurfaceSlots } from './MeetingWorkbenchSecondarySurfaceSlots';
import { useMeetingWorkbenchData } from './useMeetingWorkbenchData';
import { useMeetingWorkbenchGraphModel } from './useMeetingWorkbenchGraphModel';
import { useMeetingProductAdmission } from './useMeetingProductAdmission';
import { useMeetingMentionItems } from './useMeetingMentionItems';
import { useMeetingSessionNotification } from './useMeetingSessionNotification';
import { useMeetingWorkbenchShellState } from './useMeetingWorkbenchShellState';
import type { MeetingMissingContext } from './meetingWorkbenchStatus';
import {
  isCompactMeetingWorkbenchViewport,
  resolveMeetingWorkbenchSecondarySurface,
  useMeetingWorkbenchViewportClass,
} from './meetingWorkbenchPanelLayoutState';
import { resolveCompactMeetingInspectorTab } from './meetingWorkbenchModeSurfaceRegistry';
import type {
  AOLMeetingBottomShellProps,
  GraphViewMode,
  InspectorTab,
  MeetingInfoPanel,
  MeetingMentionItem,
  MeetingSessionSummary,
} from './meetingWorkbenchTypes';
export function AOLMeetingBottomShell({
  workspaceId,
  apiUrl,
  capabilityCode = 'ig',
  meetingId,
  summary,
  selection,
  graphSelection,
  attachResponse,
  surfaceRoute,
  onSwitchObject,
}: AOLMeetingBottomShellProps) {
  const t = useT();
  const {
    productAdmission: meetingProductAdmission,
    startBlockReason,
  } = useMeetingProductAdmission({
    capabilityCode,
    surfaceRoute,
    workspaceId,
  });
  const viewportClass = useMeetingWorkbenchViewportClass();
  const compactViewport = isCompactMeetingWorkbenchViewport(viewportClass);
  const {
    selectedNodeId, setSelectedNodeId, activeInspector, setActiveInspector,
    activeInfoPanel, setActiveInfoPanel, graphViewMode, setGraphViewMode,
    activeTraceFilter, setActiveTraceFilter, isConsoleOpen, setIsConsoleOpen,
    command, setCommand, localTasks, setLocalTasks, dispatchError, setDispatchError,
    canvasZoom, setCanvasZoom, selectedPackToolId, setSelectedPackToolId,
    appliedMentionItems, setAppliedMentionItems, isDispatching, setIsDispatching,
    activeMissingContext, setActiveMissingContext,
  } = useMeetingWorkbenchShellState();
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
    refreshMeetingSessions,
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
    productAdmission: meetingProductAdmission,
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

  const {
    graphProjection,
    nodes,
    selectedNode,
    activeWorkStatus,
    nextStepTitle,
    nextStepNodeId,
    runtimeLabel,
    missingContext,
    focusRoleLabel,
    missingContextLabel,
    selectedCommandImpact,
  } = useMeetingWorkbenchGraphModel({
    activeMeetingId,
    objectKind,
    objectTitle,
    effectiveSummary,
    effectiveAttachResponse,
    hasObjectContext,
    meetingEvents,
    meetingArtifacts,
    localTasks,
    objectGraphNodes,
    meetingArtifactsLoading,
    meetingArtifactsError,
    meetingEventsLoading,
    meetingEventsError,
    executionGraphNodes,
    executionGraphEdges,
    executionGraphLoading,
    executionGraphError,
    graphViewMode,
    selectedNodeId,
    runtimeSnapshot,
    command,
    t,
  });
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
    setActiveInfoPanel((current) => {
      const next = current === panel ? null : panel;
      if (compactViewport && next) {
        setActiveInspector(null);
        setIsConsoleOpen(false);
      }
      return next;
    });
  }

  async function handleStartBlankMeetingSession() {
    try {
      if (startBlockReason) {
        throw new Error(startBlockReason);
      }
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
    handleCanvasZoom(deltaY < 0 ? CANVAS_ZOOM_STEP : -CANVAS_ZOOM_STEP);
  }
  function handleApplyMention(item: MeetingMentionItem) {
    setAppliedMentionItems((current) => rememberAppliedMentionItem(current, item));
  }

  function handleToggleInspector(tab: InspectorTab) {
    setActiveInspector((current) => {
      const next = current === tab ? null : tab;
      if (compactViewport && next) {
        setActiveInfoPanel(null);
        setIsConsoleOpen(false);
      }
      return next;
    });
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

  const { handleCompiledGraphEnvelope, handleSubmitCommand, interactionTarget } = createMeetingWorkbenchCommandDispatchHandlers({
    command,
    activeMeetingId,
    mentionItems,
    packTools,
    selectedPackToolId,
    effectiveSummary,
    effectiveSelection,
    graphSelection,
    selectedNode,
    objectTitle,
    capabilityCode,
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

  const activeSecondarySurface = resolveMeetingWorkbenchSecondarySurface({
    activeInfoPanel,
    activeInspector,
    isConsoleOpen,
  });

  const compactInspectorTab = resolveCompactMeetingInspectorTab(activeInspector, graphViewMode);

  function handleToggleCompactInspectorPanel() {
    handleToggleInspector(compactInspectorTab);
  }

  function handleToggleConsole() {
    setIsConsoleOpen((current) => {
      const next = !current;
      if (compactViewport && next) {
        setActiveInfoPanel(null);
        setActiveInspector(null);
      }
      return next;
    });
  }

  function handleSelectMeetingSession(session: MeetingSessionSummary) {
    setActiveMeetingId(session.id);
    setSelectedNodeId('ready');
    setIsConsoleOpen(false);
    setActiveInfoPanel(null);
  }

  function handleCloseSecondarySurface() {
    setActiveInfoPanel(null);
    setActiveInspector(null);
    setIsConsoleOpen(false);
  }

  const inspectorDockProps = {
    activeInspector,
    graphViewMode,
    selectedNode,
    runtimeSnapshot,
    workspaceId,
    apiUrl,
    capabilityCode,
    meetingId: activeMeetingId,
    summary: effectiveSummary,
    attachResponse: effectiveAttachResponse,
    surfaceRoute,
    objectGraphProjections,
    objectGraphLoading,
    objectGraphError,
    commandImpact: selectedCommandImpact,
    traceEvents: graphProjection.traceEvents,
    eventCounts: graphProjection.eventCounts,
    activeTraceFilter,
    onTraceFilterChange: setActiveTraceFilter,
    onToggleInspector: handleToggleInspector,
    onClose: () => setActiveInspector(null),
    t,
  };

  const { floatingPanel, compactSecondaryDrawer } = createMeetingWorkbenchSecondarySurfaceSlots({
    compactViewport,
    activeInfoPanel,
    activeSecondarySurface,
    graphViewMode,
    nodes,
    summary: effectiveSummary,
    selection: effectiveSelection,
    attachResponse: effectiveAttachResponse,
    activeMeetingId,
    surfaceRoute,
    onSwitchObject,
    sessions: meetingSessions,
    sessionsLoading: meetingSessionsLoading,
    sessionsError: meetingSessionsError,
    creatingSession: startingBlankMeetingSession,
    createSessionError: startBlankMeetingSessionError,
    selectedNodeId,
    activeMissingContext,
    selectedNode,
    isConsoleOpen,
    onCreateSession: handleStartBlankMeetingSession,
    onRetrySessions: () => {
      void refreshMeetingSessions();
    },
    onSelectSession: handleSelectMeetingSession,
    onCloseInfoPanel: () => setActiveInfoPanel(null),
    onCloseSecondary: handleCloseSecondarySurface,
    onSelectNodeFromDrawer: (nodeId) => {
      handleSelectNode(nodeId);
      setActiveInfoPanel(null);
    },
    onSelectMissingContextFromDrawer: (context) => {
      handleSelectMissingContext(context);
      setActiveInfoPanel(null);
    },
    inspectorDockProps,
    t,
  });

  return (
    <div data-testid="aol-meeting-bottom-shell">
      <MeetingWorkbenchStageLayout
        viewportClass={viewportClass}
        headerProps={{
          activePanel: activeInfoPanel,
          activeMeetingId,
          sessionsCount: meetingSessions.length,
          sessionsLoading: meetingSessionsLoading,
          objectTitle,
          hasObjectContext,
          graphViewMode,
          primaryCount: graphProjection.primaryCount,
          traceCount: graphProjection.traceCount,
          workStatus: activeWorkStatus,
          nextStepTitle,
          runtimeLabel,
          focusRoleLabel,
          missingContextLabel,
          startingBlankMeetingSession,
          onStartBlankMeetingSession: handleStartBlankMeetingSession,
          onSelectNextStep: nextStepNodeId ? handleSelectNextStep : null,
          onSelectMissingContext: missingContext ? () => handleSelectMissingContext(missingContext) : null,
          onTogglePanel: handleToggleInfoPanel,
          showInspectorToggle: compactViewport,
          inspectorPanelActive: Boolean(activeInspector),
          onToggleInspectorPanel: handleToggleCompactInspectorPanel,
          onGraphViewModeChange: handleGraphViewModeChange,
          compactViewport,
          t,
        }}
        floatingPanel={floatingPanel}
        stageProps={{
          apiUrl,
          workspaceId,
          meetingId: activeMeetingId,
          graphViewMode,
          nodes,
          edges: graphProjection.edges,
          summary: effectiveSummary,
          attachResponse: effectiveAttachResponse,
          selectedNodeId,
          activeMissingContext,
          onSelectNode: handleSelectNode,
          onSelectMissingContext: handleSelectMissingContext,
          zoom: canvasZoom,
          onZoomIn: () => handleCanvasZoom(CANVAS_ZOOM_STEP),
          onZoomOut: () => handleCanvasZoom(-CANVAS_ZOOM_STEP),
          onResetView: () => {
            setCanvasZoom(1);
            setSelectedNodeId('ready');
          },
          onWheelZoom: handleCanvasWheelZoom,
          commandImpact: selectedCommandImpact,
          command,
          selectedPackTool: selectedPackToolId === 'auto' ? null : selectedPackToolId,
          mentionItems,
          selectedObjectRef: effectiveSummary?.ref || null,
          graphSelection,
          onCommandEnvelope: handleCompiledGraphEnvelope,
          showOutliner: !compactViewport,
          compactLayout: compactViewport,
          t,
          inspectorSlot: !compactViewport ? <MeetingWorkbenchInspectorDock {...inspectorDockProps} /> : null,
        }}
        secondaryDrawer={compactSecondaryDrawer}
        inlineConsole={isConsoleOpen ? <MeetingConsoleDrawer selectedNode={selectedNode} onClose={() => setIsConsoleOpen(false)} /> : null}
        notificationProps={sessionNotification ? {
            notification: sessionNotification,
            dismissLabel: t('meetingWorkbenchDismissNotification'),
            onClose: clearSessionNotification,
          } : null}
        commandBarProps={{
          command,
          onCommandChange: setCommand,
          onSubmitCommand: handleSubmitCommand,
          isDispatching,
          isConsoleOpen,
          onToggleConsole: handleToggleConsole,
          packTools,
          selectedPackToolId,
          onSelectedPackToolChange: setSelectedPackToolId,
          packToolsLoading,
          packToolsError,
          hasActiveMeeting: Boolean(activeMeetingId),
          mentionItems,
          mentionItemsLoading: packToolsLoading || registryMentionItemsLoading,
          mentionItemsError: registryMentionItemsError,
          onApplyMention: handleApplyMention,
          missingContextLabel,
          interactionTarget,
          t,
        }}
        dispatchError={dispatchError}
      />
    </div>
  );
}

export default AOLMeetingBottomShell;
