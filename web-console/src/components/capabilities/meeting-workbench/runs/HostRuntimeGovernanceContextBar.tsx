import type { HostRuntimeEvent } from '@/lib/host-runtime-sessions';

export function HostRuntimeGovernanceContextBar({ events }: { events: HostRuntimeEvent[] }) {
  const snapshot = [...events].reverse().find((event) => event.event_type === 'governance.snapshot.recorded');
  return (
    <div className="space-y-2 text-xs" data-testid="host-runtime-governance-context">
      <div className="font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">Governance</div>
      {snapshot ? (
        <div className="space-y-1 rounded border border-slate-200 p-2 dark:border-slate-800">
          <div className="truncate">Intent: {String((snapshot.payload.intent_ref as Record<string, unknown> | undefined)?.source || 'recorded')}</div>
          <div className="truncate">Policy: {String((snapshot.payload.policy_ref as Record<string, unknown> | undefined)?.source || 'recorded')}</div>
          <div className="truncate font-mono">{String(snapshot.payload.governance_trace_ref || '')}</div>
        </div>
      ) : (
        <div className="text-slate-500 dark:text-slate-400">Snapshot will be recorded before dispatch.</div>
      )}
    </div>
  );
}
