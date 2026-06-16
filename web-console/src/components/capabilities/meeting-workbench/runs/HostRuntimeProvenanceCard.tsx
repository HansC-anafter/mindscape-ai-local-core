import type { HostRuntimeEvent } from '@/lib/host-runtime-sessions';

export function HostRuntimeProvenanceCard({ events }: { events: HostRuntimeEvent[] }) {
  const provenance = events.filter((event) => event.event_type === 'artifact.provenance.recorded' || event.payload.artifact_ref);
  return (
    <div className="space-y-2 text-xs" data-testid="host-runtime-provenance">
      {provenance.length === 0 ? (
        <div className="text-slate-500 dark:text-slate-400">No artifact provenance yet.</div>
      ) : provenance.map((event, index) => (
        <div key={`${event.event_type}-${index}`} className="rounded border border-slate-200 p-2 dark:border-slate-800">
          <div className="font-semibold text-slate-800 dark:text-slate-100">{event.event_type}</div>
          <div className="mt-1 truncate font-mono text-slate-500 dark:text-slate-400">
            {String(event.payload.artifact_ref || event.payload.storage_ref || event.seq)}
          </div>
        </div>
      ))}
    </div>
  );
}
