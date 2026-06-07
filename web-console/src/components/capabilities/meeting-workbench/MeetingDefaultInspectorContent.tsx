import type { AddressableObjectSummary, ObjectGraphProjection, ObjectMeetingAttachResponse } from "@/lib/addressable-object-layer";
import { addressableRefKey, formatEventTime, formatKind, getEventTitle, getEventType, graphRefLabel } from "./meetingGraphProjection";
import type { InspectorTab, MeetingCommandImpact, MeetingEventSummary, MeetingNode, MeetingTranslate, RuntimeInspectorSnapshot } from "./meetingWorkbenchTypes";
import { MeetingRuntimeInspectorContent } from "./MeetingRuntimeInspectorPanel";
import { RuntimeCommandSurfaceSlot } from "./RuntimeCommandSurfaceSlot";

export function MeetingDefaultInspectorContent({
  activeInspector,
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
  t,
}: {
  activeInspector: InspectorTab;
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
  t: MeetingTranslate;
}) {
  const traceFilterOptions = Object.entries(eventCounts)
    .filter(([type, count]) => count > 0 && !type.startsWith('collapsed_') && type !== 'executable_action_item')
    .sort(([left], [right]) => left.localeCompare(right));
  const filteredTraceEvents = traceEvents.filter((event) => {
    if (!activeTraceFilter) {
      return true;
    }
    const type = getEventType(event);
    if (activeTraceFilter === 'decision') {
      return type.startsWith('decision_');
    }
    return type === activeTraceFilter;
  });
  const selectedTraceEvent = selectedNode?.eventIds?.length
    ? traceEvents.find((event) => selectedNode.eventIds?.includes(event.id)) ?? filteredTraceEvents[0] ?? null
    : filteredTraceEvents[0] ?? null;

  return (
    <>
      {activeInspector === 'object' ? (
        <div className="space-y-3">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
              Selected
            </div>
            <div className="mt-1 font-semibold text-slate-950 dark:text-slate-100">
              {summary?.title || 'Selected object'}
            </div>
            <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">
              {summary?.summary_text || 'Object context is attached to this meeting.'}
            </p>
          </div>
          <div className="rounded-md border border-slate-200 p-2 text-xs dark:border-slate-800">
            <div className="font-mono text-slate-700 dark:text-slate-200">
              {summary?.ref.uri || 'mindscape://object'}
            </div>
          </div>
        </div>
      ) : null}

      {activeInspector === 'runtime' ? (
        <MeetingRuntimeInspectorContent
          runtimeSnapshot={runtimeSnapshot}
          commandSurfaceSlot={
            <RuntimeCommandSurfaceSlot
              workspaceId={workspaceId}
              apiUrl={apiUrl}
              capabilityCode={capabilityCode}
              meetingId={meetingId}
              selectedObjectRef={attachResponse?.target_ref || summary?.ref || null}
              runtimeSnapshot={runtimeSnapshot}
              surfaceRoute={surfaceRoute || 'meeting_workbench'}
            />
          }
        />
      ) : null}

      {activeInspector === 'session' ? (
        <dl className="grid gap-2 text-xs">
          <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
            <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">Meeting</dt>
            <dd className="mt-1 font-mono">{meetingId}</dd>
          </div>
          <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
            <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">Workspace</dt>
            <dd className="mt-1 font-mono">{workspaceId}</dd>
          </div>
          <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
            <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">API</dt>
            <dd className="mt-1 truncate font-mono">{apiUrl}</dd>
          </div>
        </dl>
      ) : null}

      {activeInspector === 'trace' ? (
        <div className="space-y-3" data-testid="meeting-trace-panel">
          {commandImpact ? (
            <div className="rounded-md border border-blue-200 bg-blue-50/70 p-2 text-xs dark:border-blue-900 dark:bg-blue-950/20" data-testid="meeting-command-impact-panel">
              <div className="flex items-center justify-between gap-2">
                <div className="font-semibold text-blue-950 dark:text-blue-100">Command impact</div>
                <span className="rounded bg-white/80 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-blue-700 dark:bg-blue-950/70 dark:text-blue-200">
                  {commandImpact.phase}
                </span>
              </div>
              <div className="mt-2 rounded bg-white/80 p-2 font-medium leading-5 text-slate-900 dark:bg-slate-950/70 dark:text-slate-100">
                {commandImpact.commandText}
              </div>
              <dl className="mt-2 grid grid-cols-2 gap-1.5 text-[11px] text-slate-600 dark:text-slate-300">
                <div className="rounded bg-white/70 px-2 py-1 dark:bg-slate-950/50">
                  <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">Status</dt>
                  <dd className="mt-0.5">{commandImpact.status}</dd>
                </div>
                <div className="rounded bg-white/70 px-2 py-1 dark:bg-slate-950/50">
                  <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">Edges</dt>
                  <dd className="mt-0.5">{commandImpact.edgeIds.size}</dd>
                </div>
                <div className="rounded bg-white/70 px-2 py-1 dark:bg-slate-950/50">
                  <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">Decisions</dt>
                  <dd className="mt-0.5">{commandImpact.decisions.length}</dd>
                </div>
                <div className="rounded bg-white/70 px-2 py-1 dark:bg-slate-950/50">
                  <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">Actions</dt>
                  <dd className="mt-0.5">{commandImpact.actionItems.length}</dd>
                </div>
                <div className="rounded bg-white/70 px-2 py-1 dark:bg-slate-950/50">
                  <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">Outputs</dt>
                  <dd className="mt-0.5">{commandImpact.outputs.length}</dd>
                </div>
                <div className="rounded bg-white/70 px-2 py-1 dark:bg-slate-950/50">
                  <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">Artifacts</dt>
                  <dd className="mt-0.5">{commandImpact.artifacts.length}</dd>
                </div>
              </dl>
              <div className="mt-2 max-h-28 space-y-1 overflow-auto">
                {commandImpact.relatedNodes.slice(0, 8).map((node) => (
                  <div key={node.id} className="rounded bg-white/70 px-2 py-1 text-[11px] dark:bg-slate-950/50">
                    <span className="font-semibold">{node.eyebrow}</span>
                    <span className="mx-1 text-slate-400">/</span>
                    <span>{node.title}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          <div className="rounded-md border border-slate-200 p-2 text-xs dark:border-slate-800">
            <div className="flex items-center justify-between gap-2">
              <div className="font-semibold text-slate-900 dark:text-slate-100">Raw replay events</div>
              <div className="rounded bg-slate-100 px-1.5 py-0.5 font-semibold tabular-nums text-slate-500 dark:bg-slate-900 dark:text-slate-400">
                {filteredTraceEvents.length}/{traceEvents.length}
              </div>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => onTraceFilterChange(null)}
                className={`rounded border px-2 py-1 text-[11px] font-semibold ${
                  activeTraceFilter === null
                    ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950/40 dark:text-blue-300'
                    : 'border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-slate-800 dark:text-slate-400 dark:hover:bg-slate-900'
                }`}
                data-testid="meeting-trace-filter-all"
                aria-pressed={activeTraceFilter === null}
              >
                All
              </button>
              {traceFilterOptions.map(([type, count]) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => onTraceFilterChange(type)}
                  className={`rounded border px-2 py-1 text-[11px] font-semibold ${
                    activeTraceFilter === type
                      ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-950/40 dark:text-blue-300'
                      : 'border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-slate-800 dark:text-slate-400 dark:hover:bg-slate-900'
                  }`}
                  data-testid={`meeting-trace-filter-${type}`}
                  aria-pressed={activeTraceFilter === type}
                >
                  {formatKind(type)} {count}
                </button>
              ))}
            </div>
          </div>
          <div
            className="max-h-44 space-y-1.5 overflow-auto rounded-md border border-slate-200 p-2 dark:border-slate-800"
            data-testid="meeting-trace-event-list"
          >
            {filteredTraceEvents.slice(0, 80).map((event) => {
              const type = getEventType(event);
              return (
                <div
                  key={event.id}
                  className={`rounded px-2 py-1.5 text-xs ${
                    selectedTraceEvent?.id === event.id
                      ? 'bg-blue-50 text-blue-800 dark:bg-blue-950/30 dark:text-blue-200'
                      : 'bg-slate-50 text-slate-600 dark:bg-slate-900 dark:text-slate-300'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-semibold">{formatKind(type)}</span>
                    <span className="shrink-0 font-mono text-[10px] opacity-70">
                      {formatEventTime(event.timestamp)}
                    </span>
                  </div>
                  <div className="mt-0.5 truncate text-[11px] opacity-75">{getEventTitle(event)}</div>
                </div>
              );
            })}
            {filteredTraceEvents.length === 0 ? (
              <div className="rounded-md border border-dashed border-slate-200 px-2 py-3 text-xs text-slate-400 dark:border-slate-800 dark:text-slate-500">
                No events for this filter.
              </div>
            ) : null}
          </div>
          <pre
            className="max-h-44 overflow-auto rounded-md bg-slate-100 p-2 text-[11px] leading-5 text-slate-700 dark:bg-slate-900 dark:text-slate-300"
            data-testid="meeting-trace-event-json"
          >
            {selectedTraceEvent ? JSON.stringify(selectedTraceEvent, null, 2) : 'No event selected.'}
          </pre>
        </div>
      ) : null}

      {activeInspector === 'graph' ? (
        <div className="space-y-3" data-testid="meeting-object-graph-panel">
          <div className="rounded-md border border-slate-200 p-2 text-xs dark:border-slate-800">
            <div className="flex items-center justify-between gap-2">
              <div className="font-semibold text-slate-900 dark:text-slate-100">Bounded object graph</div>
              <div className="rounded bg-slate-100 px-1.5 py-0.5 font-semibold tabular-nums text-slate-500 dark:bg-slate-900 dark:text-slate-400">
                {objectGraphProjections.length}
              </div>
            </div>
            {objectGraphLoading ? (
              <div className="mt-2 text-slate-500 dark:text-slate-400">Loading bounded relation projections...</div>
            ) : null}
            {objectGraphError ? (
              <div className="mt-2 rounded bg-amber-50 px-2 py-1.5 text-amber-700 dark:bg-amber-950/20 dark:text-amber-300">
                {objectGraphError}
              </div>
            ) : null}
          </div>
          <div className="max-h-56 space-y-2 overflow-auto">
            {objectGraphProjections.map((projection) => (
              <div
                key={addressableRefKey(projection.ref)}
                className="rounded-md border border-slate-200 p-2 text-xs dark:border-slate-800"
              >
                <div className="font-semibold text-slate-900 dark:text-slate-100">
                  {projection.summary?.title || graphRefLabel(projection.ref)}
                </div>
                <div className="mt-1 truncate font-mono text-[11px] text-slate-500 dark:text-slate-400">
                  {projection.ref.uri || graphRefLabel(projection.ref)}
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {(projection.relations || []).slice(0, 6).map((relation, index) => (
                    <span
                      key={`${relation.relation_kind}-${index}`}
                      className="rounded-full bg-slate-100 px-2 py-1 text-[11px] text-slate-600 dark:bg-slate-900 dark:text-slate-300"
                    >
                      {relation.direction} {relation.relation_kind}
                    </span>
                  ))}
                  {(projection.relations || []).length === 0 ? (
                    <span className="text-slate-400 dark:text-slate-500">No bounded relations</span>
                  ) : null}
                </div>
              </div>
            ))}
            {objectGraphProjections.length === 0 && !objectGraphLoading ? (
              <div className="rounded-md border border-dashed border-slate-200 px-2 py-3 text-xs text-slate-400 dark:border-slate-800 dark:text-slate-500">
                No graph projection available for the selected objects.
              </div>
            ) : null}
          </div>
          {selectedNode?.lane === 'graph' && selectedNode.output ? (
            <pre className="max-h-44 overflow-auto rounded-md bg-slate-100 p-2 text-[11px] leading-5 text-slate-700 dark:bg-slate-900 dark:text-slate-300">
              {selectedNode.output}
            </pre>
          ) : null}
        </div>
      ) : null}

      {activeInspector === 'prompts' ? (
        <div className="space-y-2 text-xs">
          <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
            Next prompt is created through the command bar and appears as a task node.
          </div>
        </div>
      ) : null}

      {activeInspector === 'patch' ? (
        <div className="space-y-2 text-xs">
          {(attachResponse?.review_routes ?? []).length > 0 ? (
            attachResponse?.review_routes.map((route) => (
              <a
                key={route}
                href={route}
                className="block rounded-md border border-slate-200 p-2 text-slate-700 hover:bg-slate-50 dark:border-slate-800 dark:text-slate-200 dark:hover:bg-slate-900"
              >
                {route}
              </a>
            ))
          ) : (
            <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
              {t('meetingWorkbenchNoReviewRoutesStaged')}
            </div>
          )}
        </div>
      ) : null}
    </>
  );
}
