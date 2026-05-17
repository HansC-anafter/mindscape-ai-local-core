'use client';

import { Activity, ExternalLink, HardDrive } from 'lucide-react';

export interface HostResourceSummary {
  captured_at?: string | null;
  degraded: boolean;
  pressure_state: 'ok' | 'watch' | 'critical' | 'unknown' | string;
  free_percent: number | null;
  headroom_mb: number;
  reserved_mb: number;
  lanes: {
    busy: number;
    blocked: number;
    total: number;
  };
  heavy_consumers: Array<{
    consumer_id: string;
    label: string;
    memory_mb: number;
    memory_source?: string | null;
  }>;
  primary_blockers: Array<{
    lane_id: string;
    label: string;
    state: string;
    reason?: string | null;
  }>;
  route_controls?: {
    active: number;
    draining: number;
    targets: string[];
  };
  alerts?: Array<{
    alert_id: string;
    severity: 'critical' | 'warning' | 'info' | string;
    message: string;
    action_href?: string | null;
  }>;
  dashboard_href: string;
}

interface HostResourceStatusSummaryCardProps {
  summary: HostResourceSummary | null;
  loading: boolean;
  onOpenDashboard: () => void;
}

function pressureLabel(summary: HostResourceSummary | null, loading: boolean): string {
  if (loading && !summary) {
    return 'Loading';
  }
  if (!summary) {
    return 'Unavailable';
  }
  return summary.pressure_state || 'unknown';
}

function formatMemoryMb(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '-';
  }
  return `${Math.round(value).toLocaleString()} MB`;
}

function formatFreePercent(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '-';
  }
  return `${Math.round(value)}%`;
}

function alertClassName(severity: string | undefined): string {
  if (severity === 'critical') {
    return 'border-red-200 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200';
  }
  if (severity === 'warning') {
    return 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200';
  }
  return 'border-gray-200 bg-gray-50 text-gray-700 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-200';
}

export function HostResourceStatusSummaryCard({
  summary,
  loading,
  onOpenDashboard,
}: HostResourceStatusSummaryCardProps) {
  const topConsumer = summary?.heavy_consumers?.[0] || null;
  const lanes = summary?.lanes || { busy: 0, blocked: 0, total: 0 };
  const routeControls = summary?.route_controls || { active: 0, draining: 0, targets: [] };
  const alerts = summary?.alerts || [];
  const state = pressureLabel(summary, loading);

  return (
    <div
      className="rounded border border-gray-200 p-2 text-xs dark:border-gray-800"
      data-testid="host-resource-status-summary"
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <Activity aria-hidden="true" className="h-4 w-4 shrink-0 text-gray-500" />
          <span className="truncate font-semibold">Host Resources</span>
        </div>
        <span className="shrink-0 rounded bg-gray-100 px-2 py-0.5 font-medium text-gray-700 dark:bg-gray-900 dark:text-gray-200">
          {state}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <div className="text-[10px] font-semibold uppercase text-gray-500 dark:text-gray-400">Free</div>
          <div className="font-medium">{formatFreePercent(summary?.free_percent)}</div>
        </div>
        <div>
          <div className="text-[10px] font-semibold uppercase text-gray-500 dark:text-gray-400">Headroom</div>
          <div className="font-medium">{formatMemoryMb(summary?.headroom_mb)}</div>
        </div>
      </div>
      <div className="mt-2 flex items-start gap-2">
        <HardDrive aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-gray-500" />
        <div className="min-w-0">
          <div className="break-words text-gray-600 dark:text-gray-300">
            {lanes.busy} busy / {lanes.blocked} blocked / {lanes.total} total lanes
          </div>
          <div className="break-words text-gray-500 dark:text-gray-400">
            Top: {topConsumer ? `${topConsumer.label} ${formatMemoryMb(topConsumer.memory_mb)}` : '-'}
          </div>
          <div className="break-words text-gray-500 dark:text-gray-400">
            Reservations: {routeControls.active} active / {routeControls.draining} drain
          </div>
        </div>
      </div>
      {alerts.length ? (
        <div className="mt-2 space-y-1">
          {alerts.slice(0, 2).map((alert) => (
            <div
              key={alert.alert_id}
              className={`rounded border px-2 py-1 ${alertClassName(alert.severity)}`}
            >
              {alert.message}
            </div>
          ))}
        </div>
      ) : null}
      <button
        type="button"
        className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded border border-gray-200 px-2 py-1.5 font-semibold hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-900"
        onClick={onOpenDashboard}
      >
        <ExternalLink aria-hidden="true" className="h-4 w-4" />
        Open dashboard
      </button>
    </div>
  );
}
