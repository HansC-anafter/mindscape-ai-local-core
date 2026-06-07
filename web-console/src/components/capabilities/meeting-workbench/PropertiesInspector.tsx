import React from "react";
import { X } from "lucide-react";

import type { AddressableObjectSummary, ObjectGraphProjection, ObjectMeetingAttachResponse } from "@/lib/addressable-object-layer";
import { getInspectorTabs } from "./meetingWorkbenchConstants";
import type { GraphViewMode, InspectorTab, MeetingCommandImpact, MeetingEventSummary, MeetingNode, MeetingTranslate, RuntimeInspectorSnapshot } from "./meetingWorkbenchTypes";
import { MeetingDefaultInspectorContent } from "./MeetingDefaultInspectorContent";
import { MeetingWorkInspectorContent } from "./MeetingWorkInspectorPanel";

const DEFAULT_INSPECTOR_LABEL_KEYS: Record<InspectorTab, Parameters<MeetingTranslate>[0]> = {
  object: 'meetingWorkbenchObject',
  runtime: 'meetingWorkbenchInspectorRuntime',
  session: 'meetingWorkbenchSessions',
  trace: 'meetingWorkbenchInspectorTrace',
  graph: 'meetingWorkbenchInspectorGuidance',
  prompts: 'meetingWorkbenchInspectorActions',
  patch: 'meetingWorkbenchInspectorReview',
};

const WORK_INSPECTOR_LABEL_KEYS: Record<InspectorTab, Parameters<MeetingTranslate>[0]> = {
  object: 'meetingWorkbenchInspectorSummary',
  runtime: 'meetingWorkbenchInspectorRuntime',
  session: 'meetingWorkbenchInspectorContext',
  trace: 'meetingWorkbenchInspectorTrace',
  graph: 'meetingWorkbenchInspectorGuidance',
  prompts: 'meetingWorkbenchInspectorActions',
  patch: 'meetingWorkbenchInspectorReview',
};

function inspectorTabLabel(tab: InspectorTab, graphViewMode: GraphViewMode, t: MeetingTranslate): string {
  return t(graphViewMode === 'work' ? WORK_INSPECTOR_LABEL_KEYS[tab] : DEFAULT_INSPECTOR_LABEL_KEYS[tab]);
}

export function MeetingInspectorRail({
  activeInspector,
  graphViewMode,
  onToggleInspector,
  t,
}: {
  activeInspector: InspectorTab | null;
  graphViewMode: GraphViewMode;
  onToggleInspector: (tab: InspectorTab) => void;
  t: MeetingTranslate;
}) {
  const tabs = getInspectorTabs(graphViewMode);
  return (
    <nav
      className="flex w-12 shrink-0 flex-col items-center gap-2 border-l border-slate-200 bg-white px-1.5 py-3 dark:border-slate-800 dark:bg-slate-950"
      data-testid="meeting-inspector-rail"
      aria-label={t('meetingWorkbenchInspectorLabel')}
    >
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = tab.id === activeInspector;
        const label = inspectorTabLabel(tab.id, graphViewMode, t);
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onToggleInspector(tab.id)}
            className={`inline-flex h-9 w-9 items-center justify-center rounded-md border transition-colors ${
              isActive
                ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950/40 dark:text-blue-300'
                : 'border-transparent text-slate-500 hover:border-slate-200 hover:bg-slate-100 dark:text-slate-400 dark:hover:border-slate-800 dark:hover:bg-slate-900'
            }`}
            aria-label={t(isActive ? 'meetingWorkbenchInspectorClose' : 'meetingWorkbenchInspectorOpen', { label })}
            title={label}
            data-testid={`meeting-inspector-tab-${tab.id}`}
          >
            <Icon className="h-4 w-4" aria-hidden="true" />
          </button>
        );
      })}
    </nav>
  );
}

export function MeetingInspectorPanel({
  activeInspector,
  graphViewMode,
  selectedNode,
  runtimeSnapshot,
  workspaceId,
  apiUrl,
  capabilityCode = '',
  meetingId,
  summary,
  attachResponse,
  surfaceRoute = '',
  objectGraphProjections,
  objectGraphLoading,
  objectGraphError,
  commandImpact,
  traceEvents,
  eventCounts,
  activeTraceFilter,
  onTraceFilterChange,
  onClose,
  t,
}: {
  activeInspector: InspectorTab;
  graphViewMode: GraphViewMode;
  selectedNode: MeetingNode | null;
  runtimeSnapshot: RuntimeInspectorSnapshot;
  workspaceId: string;
  apiUrl: string;
  capabilityCode?: string;
  meetingId: string;
  summary: AddressableObjectSummary | null;
  attachResponse: ObjectMeetingAttachResponse | null;
  surfaceRoute?: string;
  objectGraphProjections: ObjectGraphProjection[];
  objectGraphLoading: boolean;
  objectGraphError: string | null;
  commandImpact: MeetingCommandImpact | null;
  traceEvents: MeetingEventSummary[];
  eventCounts: Record<string, number>;
  activeTraceFilter: string | null;
  onTraceFilterChange: (filter: string | null) => void;
  onClose: () => void;
  t: MeetingTranslate;
}) {
  const title = getInspectorTabs(graphViewMode).find((tab) => tab.id === activeInspector)
    ? inspectorTabLabel(activeInspector, graphViewMode, t)
    : 'Inspector';
  const useWorkInspectorContent = graphViewMode === 'work' && activeInspector !== 'trace';

  return (
    <aside
      className="flex w-[340px] shrink-0 flex-col border-l border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950"
      data-testid="meeting-inspector-panel"
    >
      <div className="flex h-11 shrink-0 items-center justify-between border-b border-slate-200 px-3 dark:border-slate-800">
        <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
          {title}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100"
          aria-label={t('meetingWorkbenchInspectorClose', { label: title })}
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3 text-sm text-slate-700 dark:text-slate-200">
        {useWorkInspectorContent ? (
          <MeetingWorkInspectorContent
            activeInspector={activeInspector}
            selectedNode={selectedNode}
            runtimeSnapshot={runtimeSnapshot}
            workspaceId={workspaceId}
            apiUrl={apiUrl}
            capabilityCode={capabilityCode}
            meetingId={meetingId}
            summary={summary}
            attachResponse={attachResponse}
            surfaceRoute={surfaceRoute}
            objectGraphProjections={objectGraphProjections}
            objectGraphLoading={objectGraphLoading}
            objectGraphError={objectGraphError}
            commandImpact={commandImpact}
            t={t}
          />
        ) : (
          <MeetingDefaultInspectorContent
            activeInspector={activeInspector}
            selectedNode={selectedNode}
            runtimeSnapshot={runtimeSnapshot}
            workspaceId={workspaceId}
            apiUrl={apiUrl}
            capabilityCode={capabilityCode}
            meetingId={meetingId}
            summary={summary}
            attachResponse={attachResponse}
            surfaceRoute={surfaceRoute}
            objectGraphProjections={objectGraphProjections}
            objectGraphLoading={objectGraphLoading}
            objectGraphError={objectGraphError}
            commandImpact={commandImpact}
            traceEvents={traceEvents}
            eventCounts={eventCounts}
            activeTraceFilter={activeTraceFilter}
            onTraceFilterChange={onTraceFilterChange}
            t={t}
          />
        )}

        <div className="mt-3 rounded-md border border-slate-200 p-2 text-xs dark:border-slate-800">
          <div className="font-semibold text-slate-900 dark:text-slate-100">Selected node</div>
          <div className="mt-1 text-slate-500 dark:text-slate-400">
            {selectedNode ? `${selectedNode.eyebrow}: ${selectedNode.title}` : 'none'}
          </div>
        </div>
      </div>
    </aside>
  );
}

export function MeetingConsoleDrawer({
  selectedNode,
  onClose,
}: {
  selectedNode: MeetingNode | null;
  onClose: () => void;
}) {
  return (
    <section
      className="h-[38%] max-h-40 shrink-0 border-t border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950"
      data-testid="meeting-console-drawer"
      aria-label="Meeting console"
    >
      <div className="flex h-9 items-center justify-between border-b border-slate-200 px-3 dark:border-slate-800">
        <div className="text-xs font-semibold text-slate-800 dark:text-slate-100">
          Console: {selectedNode?.title || 'Selected node'}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex h-7 w-7 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100"
          aria-label="Collapse console"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <div className="grid h-[calc(100%-2.25rem)] grid-cols-[minmax(0,1fr)_220px] gap-3 overflow-auto px-3 py-2 text-xs">
        <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
          <div className="font-semibold text-slate-900 dark:text-slate-100">Node detail</div>
          <p className="mt-1 leading-5 text-slate-500 dark:text-slate-400">
            {selectedNode?.detail || 'Select a graph node to inspect details.'}
          </p>
          {selectedNode?.output ? (
            <p className="mt-2 rounded bg-slate-100 px-2 py-1 font-mono text-[11px] text-slate-600 dark:bg-slate-900 dark:text-slate-300">
              {selectedNode.output}
            </p>
          ) : null}
        </div>
        <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
          <div className="font-semibold text-slate-900 dark:text-slate-100">Runtime output</div>
          <p className="mt-1 leading-5 text-slate-500 dark:text-slate-400">
            Waiting for the first execution event.
          </p>
        </div>
      </div>
    </section>
  );
}
