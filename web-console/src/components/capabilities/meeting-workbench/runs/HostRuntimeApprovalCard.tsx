import type { HostRuntimeEvent } from '@/lib/host-runtime-sessions';

export function HostRuntimeApprovalCard({ events }: { events: HostRuntimeEvent[] }) {
  const approvals = events.filter((event) => event.event_type.startsWith('approval.'));
  return (
    <div className="space-y-2" data-testid="host-runtime-approvals">
      {approvals.length === 0 ? (
        <div className="text-xs text-slate-500 dark:text-slate-400">No approval requests.</div>
      ) : approvals.map((event, index) => (
        <div key={`${event.event_type}-${index}`} className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-200">
          <div className="font-semibold">{event.event_type}</div>
          <div className="mt-1">{String(event.payload.approval_id || event.payload.tool || 'approval')}</div>
        </div>
      ))}
    </div>
  );
}
