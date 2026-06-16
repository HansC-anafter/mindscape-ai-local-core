import type { AddressableObjectRef } from '@/lib/addressable-object-layer';

export function HostRuntimeObjectContextBar({
  meetingId,
  selectedObjectRef,
}: {
  meetingId: string | null;
  selectedObjectRef: AddressableObjectRef | null;
}) {
  return (
    <div className="space-y-2 text-xs" data-testid="host-runtime-object-context">
      <div className="rounded border border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-950">
        <div className="font-semibold text-slate-800 dark:text-slate-100">Meeting</div>
        <div className="mt-1 truncate font-mono text-slate-500 dark:text-slate-400">{meetingId || 'No meeting'}</div>
      </div>
      <div className="rounded border border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-950">
        <div className="font-semibold text-slate-800 dark:text-slate-100">Selected object</div>
        <div className="mt-1 truncate font-mono text-slate-500 dark:text-slate-400">{selectedObjectRef?.uri || 'No object selected'}</div>
      </div>
    </div>
  );
}
