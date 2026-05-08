'use client';

import React, { useState } from 'react';
import { Box, FileText, Maximize2, Minimize2, PanelBottom } from 'lucide-react';

import type { AOLRuntimeShellState } from './AOLRuntimeShellContext';
import type { MeetingPaneSizePreset } from './RuntimeShellPanel';

interface RuntimeShellPanelFallbackBodyProps {
  state: AOLRuntimeShellState;
}

export function RuntimeShellPanelFallbackBody({
  state,
}: RuntimeShellPanelFallbackBodyProps) {
  const [activePanel, setActivePanel] = useState<'object' | 'sessions' | null>(null);
  const summary = state.resolvedObject?.summary ?? null;
  const meetingId = state.currentMeetingId || state.attachResponse?.meeting_id || 'meeting';
  const title = summary?.title || state.selection?.label || 'Meeting object';
  const owner = summary?.ref.owner_pack || state.selection?.ownerPack || 'unknown';
  const kind = summary?.ref.object_kind || state.selection?.objectKind || 'object';
  const source = summary?.ref.source_surface || state.selection?.sourceSurface || state.activeSurface?.surfaceId || 'current surface';

  return (
    <div
      className="flex h-full min-h-0 bg-slate-100 text-slate-900 dark:bg-slate-950 dark:text-slate-100"
      data-testid="aol-meeting-bottom-shell"
      data-meeting-shell-state="loading-full-workbench"
    >
      <div className="flex min-w-0 flex-1 flex-col">
        <header
          className="flex h-11 shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white px-3 dark:border-slate-800 dark:bg-slate-950"
          data-testid="meeting-header-toolbar"
        >
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              onClick={() => setActivePanel((current) => (current === 'object' ? null : 'object'))}
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
              <span className="truncate">Object</span>
              <span className="hidden max-w-[110px] truncate text-[11px] font-medium opacity-70 md:inline">
                {title}
              </span>
            </button>
            <button
              type="button"
              onClick={() => setActivePanel((current) => (current === 'sessions' ? null : 'sessions'))}
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
              <span>Sessions</span>
              <span className="rounded bg-white px-1.5 py-0.5 text-[10px] tabular-nums text-slate-500 dark:bg-slate-950 dark:text-slate-400">
                1
              </span>
            </button>
          </div>
          <div className="hidden min-w-0 items-center gap-2 text-xs text-slate-500 dark:text-slate-400 sm:flex">
            <span className="truncate rounded bg-slate-100 px-2 py-1 font-medium text-slate-700 dark:bg-slate-900 dark:text-slate-200">
              {title}
            </span>
            <span className="truncate font-mono text-slate-700 dark:text-slate-200">{meetingId}</span>
          </div>
        </header>
        <div className="relative min-h-0 flex-1 overflow-hidden">
          {activePanel === 'object' ? (
            <div className="pointer-events-none absolute left-3 top-3 z-30 h-[calc(100%-1.5rem)] w-[min(340px,calc(100%-1.5rem))]">
              <section
                className="pointer-events-auto flex max-h-full w-full flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-950"
                id="meeting-object-context-panel"
                data-testid="meeting-object-context-panel"
                aria-label="Meeting object context"
              >
                <div className="flex h-10 shrink-0 items-center justify-between border-b border-slate-200 px-3 dark:border-slate-800">
                  <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
                    Object Context
                  </div>
                  <button
                    type="button"
                    onClick={() => setActivePanel(null)}
                    className="rounded-md px-2 py-1 text-xs text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100"
                  >
                    Close
                  </button>
                </div>
                <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-auto p-3 text-xs text-slate-700 dark:text-slate-200">
                  <h2 className="truncate text-sm font-semibold text-slate-950 dark:text-slate-100">{title}</h2>
                  <div className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-2 dark:border-slate-800 dark:bg-slate-900/70">
                    <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">Meeting</div>
                    <div className="mt-1 font-mono">{meetingId}</div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="min-w-0 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-2 dark:border-slate-800 dark:bg-slate-900/70">
                      <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">Owner</div>
                      <div className="mt-1 truncate font-medium">{owner}</div>
                    </div>
                    <div className="min-w-0 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-2 dark:border-slate-800 dark:bg-slate-900/70">
                      <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">Kind</div>
                      <div className="mt-1 truncate font-medium">{kind}</div>
                    </div>
                  </div>
                  <div className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-2 dark:border-slate-800 dark:bg-slate-900/70">
                    <div className="text-[10px] uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">Source</div>
                    <div className="mt-1 truncate">{source}</div>
                  </div>
                </div>
              </section>
            </div>
          ) : null}
          {activePanel === 'sessions' ? (
            <div
              className="pointer-events-auto absolute left-3 right-3 top-3 z-30 rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-600 shadow-xl dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300 md:right-16"
              id="meeting-sessions-popover"
              data-testid="meeting-sessions-popover"
            >
              <div className="font-mono">{meetingId}</div>
            </div>
          ) : null}
          <div className="flex h-full items-center justify-center text-xs text-slate-500 dark:text-slate-400">
            Preparing runtime graph...
          </div>
        </div>
      </div>
    </div>
  );
}

interface RuntimeShellPanelFallbackProps {
  state: AOLRuntimeShellState;
  paneHeight: number;
  onClose: () => void;
  onResizeStart: (event: React.PointerEvent<HTMLButtonElement>) => void;
  onSizePreset: (preset: MeetingPaneSizePreset) => void;
}

export function RuntimeShellPanelFallback({
  state,
  paneHeight,
  onClose,
  onResizeStart,
  onSizePreset,
}: RuntimeShellPanelFallbackProps) {
  if (state.mode !== 'meeting_opened' || !state.activeSurface) {
    return null;
  }

  return (
    <section
      className="relative z-[50] flex shrink-0 flex-col border-t border-slate-200 bg-white shadow-[0_-12px_30px_rgba(15,23,42,0.12)] dark:border-slate-700 dark:bg-slate-950"
      data-testid="aol-meeting-pane"
      role="region"
      aria-label="AOL Runtime Workbench meeting view"
      style={{ height: `${paneHeight}px` }}
    >
      <div className="relative flex h-9 shrink-0 items-center justify-center border-b border-slate-200 bg-slate-100/90 dark:border-slate-800 dark:bg-slate-900/90">
        <div className="absolute left-4 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
          Meeting Workbench
        </div>
        <button
          type="button"
          onPointerDown={onResizeStart}
          className="inline-flex touch-none cursor-row-resize items-center justify-center rounded-full px-4 py-2"
          data-testid="aol-meeting-pane-resize-handle"
          aria-label="Resize meeting pane"
        >
          <span className="h-1.5 w-16 rounded-full bg-slate-400/80 transition-colors hover:bg-slate-500 dark:bg-slate-500 dark:hover:bg-slate-400" />
        </button>
        <div className="absolute right-20 flex items-center gap-1">
          <button
            type="button"
            onClick={() => onSizePreset('compact')}
            className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
            data-testid="aol-meeting-pane-compact"
            aria-label="Compact meeting workbench"
            title="Compact"
          >
            <Minimize2 className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => onSizePreset('default')}
            className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
            data-testid="aol-meeting-pane-default"
            aria-label="Default meeting workbench size"
            title="Default"
          >
            <PanelBottom className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => onSizePreset('expanded')}
            className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-200 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
            data-testid="aol-meeting-pane-expanded"
            aria-label="Expand meeting workbench"
            title="Expand"
          >
            <Maximize2 className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="absolute right-3 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-200 hover:text-slate-900 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100"
        >
          Close
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        <RuntimeShellPanelFallbackBody state={state} />
      </div>
    </section>
  );
}
