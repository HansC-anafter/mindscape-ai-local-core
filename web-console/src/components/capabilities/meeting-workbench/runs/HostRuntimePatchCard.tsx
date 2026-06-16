import type { HostRuntimeEvent } from '@/lib/host-runtime-sessions';

export function HostRuntimePatchCard({ events }: { events: HostRuntimeEvent[] }) {
  const patchEvents = events.filter((event) => event.event_type === 'patch.proposed' || event.event_type === 'file.changed');
  return (
    <div className="space-y-2" data-testid="host-runtime-patches">
      {patchEvents.length === 0 ? (
        <div className="text-xs text-slate-500 dark:text-slate-400">No file changes proposed.</div>
      ) : patchEvents.map((event, index) => (
        <div key={`${event.event_type}-${index}`} className="rounded border border-slate-200 p-2 text-xs dark:border-slate-800">
          <div className="font-semibold text-slate-800 dark:text-slate-100">{event.event_type}</div>
          <div className="mt-1 truncate font-mono text-slate-500 dark:text-slate-400">
            {Array.isArray(event.payload.files) ? event.payload.files.join(', ') : String(event.payload.path || 'change')}
          </div>
        </div>
      ))}
    </div>
  );
}
