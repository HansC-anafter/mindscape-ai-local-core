import React, { useRef, useState } from 'react';
import { Box, FileText, MousePointer2, RotateCcw, ZoomIn, ZoomOut } from 'lucide-react';

import {
  CANVAS_ZOOM_STEP,
  GRAPH_LANES,
  MAX_CANVAS_ZOOM,
  MIN_CANVAS_ZOOM,
  MIN_DISCRETE_WHEEL_ZOOM_DELTA,
} from './meetingWorkbenchConstants';
import type { CompositionGraphCommandEnvelopeDraft } from '@/lib/composition-graph';
import { DirectorGraphCanvas } from './director-graph/DirectorGraphCanvas';
import { MeetingLaneBoard } from './MeetingLaneBoard';
import { MeetingWorkSubgraphCanvas } from './MeetingWorkSubgraphCanvas';
import type {
  GraphViewMode,
  MeetingCommandImpact,
  MeetingGraphEdge,
  MeetingInfoPanel,
  MeetingNode,
  MeetingTranslate,
} from './meetingWorkbenchTypes';
import { shortId } from './meetingWorkbenchUtils';

export function clampCanvasZoom(value: number): number {
  return Math.min(MAX_CANVAS_ZOOM, Math.max(MIN_CANVAS_ZOOM, Number(value.toFixed(2))));
}

function shouldZoomMeetingCanvasFromWheel(event: React.WheelEvent<HTMLElement>): boolean {
  if (event.deltaY === 0 || Math.abs(event.deltaX) > 0) {
    return false;
  }

  const target = event.target as HTMLElement | null;
  if (target?.closest('[data-meeting-node="true"], [data-meeting-lane-scroll="true"]')) {
    return false;
  }

  if (event.deltaMode === 1 || event.deltaMode === 2) {
    return true;
  }

  return Math.abs(event.deltaY) >= MIN_DISCRETE_WHEEL_ZOOM_DELTA && Number.isInteger(event.deltaY);
}

export function MeetingHeaderToolbar({
  activePanel,
  activeMeetingId,
  sessionsCount,
  sessionsLoading,
  objectTitle,
  hasObjectContext,
  graphViewMode,
  primaryCount,
  traceCount,
  workStatus,
  nextStepTitle,
  runtimeLabel,
  focusRoleLabel,
  missingContextLabel,
  onSelectNextStep,
  onSelectMissingContext,
  onTogglePanel,
  onGraphViewModeChange,
  t,
}: {
  activePanel: MeetingInfoPanel | null;
  activeMeetingId: string;
  sessionsCount: number;
  sessionsLoading: boolean;
  objectTitle: string;
  hasObjectContext: boolean;
  graphViewMode: GraphViewMode;
  primaryCount: number;
  traceCount: number;
  workStatus: string;
  nextStepTitle: string;
  runtimeLabel: string;
  focusRoleLabel: string | null;
  missingContextLabel: string | null;
  onSelectNextStep: (() => void) | null;
  onSelectMissingContext: (() => void) | null;
  onTogglePanel: (panel: MeetingInfoPanel) => void;
  onGraphViewModeChange: (mode: GraphViewMode) => void;
  t: MeetingTranslate;
}) {
  return (
    <header
      className="flex h-11 shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white px-3 dark:border-slate-800 dark:bg-slate-950"
      data-testid="meeting-header-toolbar"
    >
      <div className="flex min-w-0 items-center gap-2">
        <button
          type="button"
          onClick={() => onTogglePanel('object')}
          className={`inline-flex h-8 max-w-[220px] items-center gap-2 rounded-md border px-2.5 text-xs font-semibold transition-colors ${
            activePanel === 'object'
              ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950/40 dark:text-blue-300'
              : 'border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800'
          }`}
          data-testid="meeting-object-context-toggle"
          aria-expanded={activePanel === 'object'}
          aria-controls="meeting-object-context-panel"
        >
          <Box className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="truncate">{t('meetingWorkbenchObject')}</span>
          <span className="hidden max-w-[110px] truncate text-[11px] font-medium opacity-70 md:inline">
            {hasObjectContext ? objectTitle : t('meetingWorkbenchBrowser')}
          </span>
        </button>
        <button
          type="button"
          onClick={() => onTogglePanel('sessions')}
          className={`inline-flex h-8 items-center gap-2 rounded-md border px-2.5 text-xs font-semibold transition-colors ${
            activePanel === 'sessions'
              ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950/40 dark:text-blue-300'
              : 'border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800'
          }`}
          data-testid="meeting-sessions-toggle"
          aria-expanded={activePanel === 'sessions'}
          aria-controls="meeting-sessions-popover"
        >
          <FileText className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{t('meetingWorkbenchSessions')}</span>
          <span className="rounded bg-white px-1.5 py-0.5 text-[10px] tabular-nums text-slate-500 dark:bg-slate-950 dark:text-slate-400">
            {sessionsLoading ? '...' : sessionsCount}
          </span>
        </button>
        <div
          className="hidden items-center overflow-hidden rounded-md border border-slate-200 bg-slate-50 p-0.5 dark:border-slate-800 dark:bg-slate-900 md:flex"
          data-testid="meeting-graph-view-mode"
          aria-label={t('meetingWorkbenchViewModeLabel')}
        >
          {(['work', 'director', 'runs', 'trace'] as GraphViewMode[]).map((mode) => {
            const isActive = graphViewMode === mode;
            const label = mode === 'work'
              ? t('meetingWorkbenchWork')
              : mode === 'director'
                ? t('meetingWorkbenchDirectorGraph')
                : mode;
            return (
              <button
                key={mode}
                type="button"
                onClick={() => onGraphViewModeChange(mode)}
                className={`h-7 rounded px-2 text-[11px] font-semibold uppercase tracking-[0.08em] transition-colors ${
                  isActive
                    ? 'bg-white text-blue-700 shadow-sm dark:bg-slate-950 dark:text-blue-300'
                    : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100'
                }`}
                data-testid={`meeting-graph-view-${mode}`}
                aria-pressed={isActive}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>
      <div
        className="hidden min-w-0 items-center gap-2 text-xs text-slate-500 dark:text-slate-400 sm:flex"
        data-testid="meeting-work-context-bar"
      >
        {graphViewMode === 'work' ? (
          <>
            <span className="truncate rounded bg-slate-100 px-2 py-1 font-medium text-slate-700 dark:bg-slate-900 dark:text-slate-200">
              {t('meetingWorkbenchFocusPrefix', {
                value: hasObjectContext ? objectTitle : t('meetingWorkbenchNoFocusObject'),
              })}
            </span>
            {focusRoleLabel ? (
              <span
                className="shrink-0 rounded bg-indigo-50 px-2 py-1 font-medium text-indigo-700 dark:bg-indigo-950/30 dark:text-indigo-300"
                data-testid="meeting-work-role-chip"
              >
                {t('meetingWorkbenchRolePrefix', { value: focusRoleLabel })}
              </span>
            ) : null}
            <span
              className="shrink-0 rounded bg-emerald-50 px-2 py-1 font-semibold text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300"
              data-testid="meeting-work-status-chip"
            >
              {workStatus}
            </span>
            <span className="max-w-[180px] truncate rounded bg-blue-50 px-2 py-1 font-medium text-blue-700 dark:bg-blue-950/30 dark:text-blue-300">
              {runtimeLabel}
            </span>
            <button
              type="button"
              onClick={onSelectNextStep ?? undefined}
              disabled={!onSelectNextStep}
              className="max-w-[220px] truncate rounded bg-slate-100 px-2 py-1 text-left font-medium text-slate-600 transition-colors hover:bg-slate-200 disabled:cursor-default disabled:hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:disabled:hover:bg-slate-900"
              data-testid="meeting-work-next-chip"
              title={nextStepTitle}
            >
              {t('meetingWorkbenchNextPrefix', { value: nextStepTitle })}
            </button>
            {missingContextLabel ? (
              <button
                type="button"
                onClick={onSelectMissingContext ?? undefined}
                disabled={!onSelectMissingContext}
                className="shrink-0 rounded bg-amber-50 px-2 py-1 text-left font-semibold text-amber-700 transition-colors hover:bg-amber-100 disabled:cursor-default disabled:hover:bg-amber-50 dark:bg-amber-950/30 dark:text-amber-300 dark:hover:bg-amber-950/50 dark:disabled:hover:bg-amber-950/30"
                data-testid="meeting-work-missing-context-chip"
                title={missingContextLabel}
              >
                {t('meetingWorkbenchMissingContextPrefix', { value: missingContextLabel })}
              </button>
            ) : null}
          </>
        ) : graphViewMode === 'director' ? (
          <>
            <span className="truncate rounded bg-slate-100 px-2 py-1 font-medium text-slate-600 dark:bg-slate-900 dark:text-slate-300">
              {t('directorGraphContextBar')}
            </span>
            <span className="shrink-0 font-semibold uppercase tracking-[0.12em]">{t('meetingWorkbenchActive')}</span>
            <span className="truncate font-mono text-slate-700 dark:text-slate-200">{shortId(activeMeetingId)}</span>
          </>
        ) : (
          <>
            <span className="truncate rounded bg-slate-100 px-2 py-1 font-medium text-slate-600 dark:bg-slate-900 dark:text-slate-300">
              {graphViewMode} - {primaryCount} nodes - {traceCount} trace events
            </span>
            <span className="shrink-0 font-semibold uppercase tracking-[0.12em]">{t('meetingWorkbenchActive')}</span>
            <span className="truncate font-mono text-slate-700 dark:text-slate-200">{shortId(activeMeetingId)}</span>
          </>
        )}
      </div>
    </header>
  );
}

export function MeetingTaskCanvas({
  apiUrl,
  workspaceId,
  meetingId,
  nodes,
  edges,
  selectedNodeId,
  onSelectNode,
  zoom,
  onZoomIn,
  onZoomOut,
  onResetView,
  onWheelZoom,
  commandImpact,
  graphViewMode,
  command,
  selectedPackTool,
  onCommandEnvelope,
  t,
}: {
  apiUrl: string;
  workspaceId: string;
  meetingId: string | null;
  nodes: MeetingNode[];
  edges: MeetingGraphEdge[];
  selectedNodeId: string;
  onSelectNode: (nodeId: string) => void;
  zoom: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onResetView: () => void;
  onWheelZoom: (deltaY: number) => void;
  commandImpact: MeetingCommandImpact | null;
  graphViewMode: GraphViewMode;
  command: string;
  selectedPackTool: string | null;
  onCommandEnvelope: (envelope: CompositionGraphCommandEnvelopeDraft) => Promise<void>;
  t: MeetingTranslate;
}) {
  const viewportRef = useRef<HTMLElement | null>(null);
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    panX: number;
    panY: number;
  } | null>(null);
  const [isDraggingCanvas, setIsDraggingCanvas] = useState(false);
  const [canvasPan, setCanvasPan] = useState({ x: 0, y: 0 });

  if (graphViewMode === 'director') {
    return (
      <DirectorGraphCanvas
        apiUrl={apiUrl}
        workspaceId={workspaceId}
        meetingId={meetingId}
        threadId={meetingId}
        command={command}
        selectedPackTool={selectedPackTool}
        onCommandEnvelope={onCommandEnvelope}
        t={t}
      />
    );
  }

  return (
    <section
      ref={viewportRef}
      className={`relative min-h-0 flex-1 overflow-auto bg-slate-100/80 px-4 py-3 dark:bg-slate-950/80 ${
        isDraggingCanvas ? 'cursor-grabbing' : 'cursor-grab'
      }`}
      data-testid="meeting-task-canvas"
      aria-label={t('meetingWorkbenchTaskGraphLabel')}
      onPointerDown={(event) => {
        if ((event.target as HTMLElement).closest('[data-meeting-node="true"], button, input, a')) {
          return;
        }

        dragRef.current = {
          pointerId: event.pointerId,
          startX: event.clientX,
          startY: event.clientY,
          panX: canvasPan.x,
          panY: canvasPan.y,
        };
        setIsDraggingCanvas(true);
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={(event) => {
        const drag = dragRef.current;
        if (!drag || drag.pointerId !== event.pointerId) {
          return;
        }

        setCanvasPan({
          x: drag.panX + event.clientX - drag.startX,
          y: drag.panY + event.clientY - drag.startY,
        });
      }}
      onPointerUp={(event) => {
        if (dragRef.current?.pointerId === event.pointerId) {
          dragRef.current = null;
          setIsDraggingCanvas(false);
          event.currentTarget.releasePointerCapture(event.pointerId);
        }
      }}
      onPointerCancel={(event) => {
        if (dragRef.current?.pointerId === event.pointerId) {
          dragRef.current = null;
          setIsDraggingCanvas(false);
        }
      }}
      onWheel={(event) => {
        if (!shouldZoomMeetingCanvasFromWheel(event)) {
          return;
        }
        event.preventDefault();
        const nextZoom = clampCanvasZoom(zoom + (event.deltaY < 0 ? CANVAS_ZOOM_STEP : -CANVAS_ZOOM_STEP));
        if (nextZoom !== zoom) {
          const rect = event.currentTarget.getBoundingClientRect();
          const anchorX = event.clientX - rect.left;
          const anchorY = event.clientY - rect.top;
          setCanvasPan((current) => ({
            x: anchorX - ((anchorX - current.x) * nextZoom) / zoom,
            y: anchorY - ((anchorY - current.y) * nextZoom) / zoom,
          }));
        }
        onWheelZoom(event.deltaY);
      }}
    >
      <div className="absolute right-3 top-3 z-10 flex items-center gap-1 rounded-md border border-slate-200 bg-white/95 p-1 shadow-sm dark:border-slate-800 dark:bg-slate-950/95">
        <button
          type="button"
          onClick={onZoomOut}
          className="inline-flex h-8 w-8 items-center justify-center rounded text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100"
          data-testid="meeting-canvas-zoom-out"
          aria-label={t('meetingWorkbenchZoomOutGraph')}
          title={t('meetingWorkbenchZoomOut')}
        >
          <ZoomOut className="h-4 w-4" aria-hidden="true" />
        </button>
        <div className="min-w-12 text-center text-[11px] font-semibold tabular-nums text-slate-500 dark:text-slate-400">
          {Math.round(zoom * 100)}%
        </div>
        <button
          type="button"
          onClick={onZoomIn}
          className="inline-flex h-8 w-8 items-center justify-center rounded text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100"
          data-testid="meeting-canvas-zoom-in"
          aria-label={t('meetingWorkbenchZoomInGraph')}
          title={t('meetingWorkbenchZoomIn')}
        >
          <ZoomIn className="h-4 w-4" aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={() => {
            setCanvasPan({ x: 0, y: 0 });
            onResetView();
          }}
          className="inline-flex h-8 w-8 items-center justify-center rounded text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100"
          data-testid="meeting-canvas-fit"
          aria-label={t('meetingWorkbenchFitGraphView')}
          title={t('meetingWorkbenchFit')}
        >
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      <div className="absolute left-3 top-3 z-10 hidden items-center gap-1 rounded-md bg-white/80 px-2 py-1 text-[11px] text-slate-500 shadow-sm dark:bg-slate-950/80 dark:text-slate-400 md:flex">
        <MousePointer2 className="h-3.5 w-3.5" aria-hidden="true" />
        {t('meetingWorkbenchCanvasHint')}
      </div>

      <div className="flex min-h-full items-start justify-center pb-4 pt-16">
        <div
          className="w-max"
          style={{
            transform: `translate(${canvasPan.x}px, ${canvasPan.y}px) scale(${zoom})`,
            transformOrigin: 'center center',
          }}
          data-testid="meeting-graph-canvas-content"
        >
          {graphViewMode === 'work' ? (
            <MeetingWorkSubgraphCanvas
              nodes={nodes}
              edges={edges}
              selectedNodeId={selectedNodeId}
              commandImpact={commandImpact}
              onSelectNode={onSelectNode}
              t={t}
            />
          ) : (
            <MeetingLaneBoard
              nodes={nodes}
              laneConfigs={GRAPH_LANES}
              selectedNodeId={selectedNodeId}
              commandImpact={commandImpact}
              onSelectNode={onSelectNode}
            />
          )}
        </div>
      </div>
    </section>
  );
}
