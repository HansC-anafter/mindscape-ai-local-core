'use client';

import React, { Suspense, lazy, type ComponentType } from 'react';
import { Maximize2, Minimize2, PanelBottom } from 'lucide-react';

import type { AOLRuntimeShellState } from './AOLRuntimeShellContext';
import { RuntimeShellPanelFallbackBody } from './RuntimeShellPanelFallback';
import type { AOLMeetingBottomShellProps } from '../meeting-workbench/meetingWorkbenchTypes';

export type MeetingPaneSizePreset = 'compact' | 'default' | 'expanded';

export interface RuntimeShellPanelProps {
  state: AOLRuntimeShellState;
  paneHeight: number;
  onClose: () => void;
  onResizeStart: (event: React.PointerEvent<HTMLButtonElement>) => void;
  onSizePreset: (preset: MeetingPaneSizePreset) => void;
  onSwitchObject: () => void;
}

type AOLMeetingBottomShellModule = {
  default: ComponentType<AOLMeetingBottomShellProps>;
};

let meetingBottomShellPromise: Promise<AOLMeetingBottomShellModule> | null = null;

export function preloadRuntimeShellPanelBody(): Promise<AOLMeetingBottomShellModule> {
  meetingBottomShellPromise ??= import('../meeting-workbench/AOLMeetingBottomShell').then((module) => ({
    default: module.AOLMeetingBottomShell,
  }));
  return meetingBottomShellPromise;
}

const AOLMeetingBottomShellLazy = lazy(preloadRuntimeShellPanelBody);

export function RuntimeShellPanel({
  state,
  paneHeight,
  onClose,
  onResizeStart,
  onSizePreset,
  onSwitchObject,
}: RuntimeShellPanelProps) {
  if (state.mode !== 'meeting_opened' || !state.activeSurface) {
    return null;
  }

  const summary = state.resolvedObject?.summary ?? null;

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
        <Suspense fallback={<RuntimeShellPanelFallbackBody state={state} />}>
          <AOLMeetingBottomShellLazy
            workspaceId={state.activeSurface.workspaceId}
            apiUrl={state.activeSurface.apiUrl}
            capabilityCode={state.activeSurface.capabilityCode}
            meetingId={state.currentMeetingId}
            summary={summary}
            selection={state.selection}
            attachResponse={state.attachResponse}
            surfaceRoute={state.activeSurface.route}
            onSwitchObject={onSwitchObject}
          />
        </Suspense>
      </div>
    </section>
  );
}

export default RuntimeShellPanel;
