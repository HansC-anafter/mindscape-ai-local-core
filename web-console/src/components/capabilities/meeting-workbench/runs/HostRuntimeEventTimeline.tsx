import type { HostRuntimeEvent } from '@/lib/host-runtime-sessions';

import { HostRuntimeStatusBadge } from './HostRuntimeStatusBadge';

export function HostRuntimeEventTimeline({
  events,
}: {
  events: HostRuntimeEvent[];
}) {
  const visibleEvents = events.slice(-24);
  return (
    <div className="flex h-full min-h-0 flex-col gap-2" data-testid="host-runtime-event-timeline">
      {visibleEvents.length === 0 ? (
        <div className="rounded-md border border-dashed border-slate-200 p-3 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
          No host runtime events yet.
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-auto space-y-2">
          {visibleEvents.map((event, index) => (
            <div
              key={`${event.seq ?? 'live'}-${event.event_type}-${index}`}
              className="rounded-md border border-slate-200 bg-white p-2 text-xs dark:border-slate-800 dark:bg-slate-950"
              data-testid={`host-runtime-event-${event.event_type}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-slate-800 dark:text-slate-100">{event.event_type}</span>
                <HostRuntimeStatusBadge status={String(event.payload.status || event.payload.reason || event.event_type)} />
              </div>
              {event.payload.delta ? (
                <div className="mt-1 text-sm text-slate-700 dark:text-slate-200">{String(event.payload.delta)}</div>
              ) : null}
              {event.payload.reason ? (
                <div className="mt-1 text-slate-500 dark:text-slate-400">{String(event.payload.reason)}</div>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
