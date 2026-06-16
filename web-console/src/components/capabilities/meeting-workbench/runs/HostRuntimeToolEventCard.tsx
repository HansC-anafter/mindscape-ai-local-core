import type { HostRuntimeEvent } from '@/lib/host-runtime-sessions';

export function HostRuntimeToolEventCard({ events }: { events: HostRuntimeEvent[] }) {
  const toolEvents = events.filter((event) => event.event_type.startsWith('tool.'));
  return (
    <div className="space-y-2" data-testid="host-runtime-tool-events">
      {toolEvents.length === 0 ? (
        <div className="text-xs text-slate-500 dark:text-slate-400">No tool calls.</div>
      ) : toolEvents.map((event, index) => (
        <div key={`${event.event_type}-${index}`} className="rounded border border-slate-200 p-2 text-xs dark:border-slate-800">
          <div className="font-semibold text-slate-800 dark:text-slate-100">{event.event_type}</div>
          <div className="mt-1 truncate text-slate-500 dark:text-slate-400">
            {String(event.payload.tool || event.payload.name || event.item_id || 'tool')}
          </div>
        </div>
      ))}
    </div>
  );
}
