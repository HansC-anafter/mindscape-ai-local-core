import { Cpu } from 'lucide-react';
import type { ReactNode } from 'react';

import type { RuntimeInspectorSnapshot } from './meetingWorkbenchTypes';

export function MeetingRuntimeInspectorContent({
  runtimeSnapshot,
  commandSurfaceSlot = null,
}: {
  runtimeSnapshot: RuntimeInspectorSnapshot;
  commandSurfaceSlot?: ReactNode;
}) {
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-slate-200 p-3 dark:border-slate-800">
        <div className="flex items-center gap-2 font-semibold text-slate-950 dark:text-slate-100">
          <Cpu className="h-4 w-4" aria-hidden="true" />
          Runtime binding
        </div>
        <div className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
          Runtime state is inspector-scoped so it does not permanently consume bottom shell width.
        </div>
        <dl className="mt-3 grid gap-2 text-xs">
          <div className="rounded-md bg-slate-50 px-2 py-1.5 dark:bg-slate-900">
            <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">Resolved</dt>
            <dd className="mt-1 font-mono text-slate-800 dark:text-slate-100">
              {runtimeSnapshot.resolvedRuntime || 'Mindscape default'}
            </dd>
          </div>
          <div className="rounded-md bg-slate-50 px-2 py-1.5 dark:bg-slate-900">
            <dt className="font-semibold uppercase tracking-[0.12em] text-slate-500">Dispatch chain</dt>
            <dd className="mt-1 truncate font-mono text-slate-800 dark:text-slate-100">
              {runtimeSnapshot.dispatchChain.length > 0
                ? runtimeSnapshot.dispatchChain.join(' -> ')
                : 'default'}
            </dd>
          </div>
        </dl>
        {runtimeSnapshot.loading ? (
          <div className="mt-3 rounded-md bg-slate-100 px-2 py-1.5 text-xs text-slate-500 dark:bg-slate-900 dark:text-slate-400">
            Loading runtime state...
          </div>
        ) : null}
        {runtimeSnapshot.error ? (
          <div className="mt-3 rounded-md bg-amber-50 px-2 py-1.5 text-xs text-amber-700 dark:bg-amber-950/20 dark:text-amber-300">
            {runtimeSnapshot.error}
          </div>
        ) : null}
        <div className="mt-3 space-y-1.5">
          {runtimeSnapshot.agents.slice(0, 5).map((agent) => {
            const isBound =
              runtimeSnapshot.boundRuntimeIds.includes(agent.id) ||
              runtimeSnapshot.resolvedRuntime === agent.id;
            const isAvailable = agent.status === 'available';
            const badgeLabel = isAvailable && isBound
              ? 'bound live'
              : isAvailable
                ? 'available'
                : isBound
                  ? 'route-bound'
                  : 'offline';
            return (
              <div
                key={agent.id}
                className="rounded-md border border-slate-200 px-2 py-1.5 text-xs dark:border-slate-800"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-semibold text-slate-800 dark:text-slate-100">
                    {agent.name || agent.id}
                  </span>
                  <span
                    className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                      isAvailable
                        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300'
                        : isBound
                          ? 'bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-300'
                          : 'bg-slate-100 text-slate-500 dark:bg-slate-900 dark:text-slate-400'
                    }`}
                  >
                    {badgeLabel}
                  </span>
                </div>
                {isBound && !isAvailable ? (
                  <div className="mt-1 text-slate-500 dark:text-slate-400">
                    Route is configured, but no live workspace bridge is reporting availability.
                  </div>
                ) : null}
                {agent.reason || agent.transport ? (
                  <div className="mt-1 truncate text-slate-500 dark:text-slate-400">
                    {agent.transport || agent.reason}
                  </div>
                ) : null}
              </div>
            );
          })}
          {runtimeSnapshot.agents.length === 0 && !runtimeSnapshot.loading ? (
            <div className="rounded-md border border-slate-200 px-2 py-1.5 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
              No runtime agents reported.
            </div>
          ) : null}
        </div>
      </div>
      {commandSurfaceSlot}
    </div>
  );
}
