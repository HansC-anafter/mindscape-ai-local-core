import { Activity, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';

export function HostRuntimeStatusBadge({
  status,
}: {
  status: string;
}) {
  const normalized = status.toLowerCase();
  const Icon = normalized.includes('failed') || normalized.includes('unavailable')
    ? AlertCircle
    : normalized.includes('running')
      ? Loader2
      : normalized.includes('ready') || normalized.includes('completed')
        ? CheckCircle2
        : Activity;
  const tone = normalized.includes('failed') || normalized.includes('unavailable')
    ? 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/50 dark:bg-rose-950/20 dark:text-rose-300'
    : normalized.includes('running')
      ? 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900/50 dark:bg-blue-950/20 dark:text-blue-300'
      : normalized.includes('ready') || normalized.includes('completed')
        ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-300'
        : 'border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-300';
  return (
    <span className={`inline-flex items-center gap-1 rounded border px-2 py-1 text-[11px] font-semibold ${tone}`}>
      <Icon className={`h-3.5 w-3.5 ${normalized.includes('running') ? 'animate-spin' : ''}`} aria-hidden="true" />
      {status}
    </span>
  );
}
