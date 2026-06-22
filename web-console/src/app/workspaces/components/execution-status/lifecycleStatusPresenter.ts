export interface LifecycleSummary {
  status?: string | null;
  phase?: string | null;
  label?: string | null;
  terminal?: boolean | null;
  owner?: string | null;
  next_step?: string | null;
}

export interface PresentedLifecycleStatus {
  label: string;
  detail: string;
  tone: 'success' | 'info' | 'warning' | 'danger' | 'neutral';
  terminal: boolean;
}

const SUCCESS_STATUSES = new Set(['completed', 'done', 'succeeded', 'success']);
const DANGER_STATUSES = new Set(['failed', 'error', 'timeout']);
const WARNING_STATUSES = new Set(['blocked', 'paused', 'waiting', 'waiting_confirmation']);
const INFO_STATUSES = new Set(['in_progress', 'processing', 'running']);

function normalize(value: string | null | undefined): string {
  return (value || '').trim().toLowerCase();
}

function titleize(value: string): string {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

export function presentLifecycleStatus(
  lifecycleSummary?: LifecycleSummary | null,
  fallbackStatus?: string | null,
): PresentedLifecycleStatus | null {
  const status = normalize(lifecycleSummary?.status || fallbackStatus);
  const phase = normalize(lifecycleSummary?.phase);
  if (!status && !phase && !lifecycleSummary?.label) return null;

  const terminal = Boolean(lifecycleSummary?.terminal) || SUCCESS_STATUSES.has(status);
  const label = lifecycleSummary?.label || titleize(phase || status || 'unknown');
  const detail =
    lifecycleSummary?.next_step ||
    lifecycleSummary?.owner ||
    (terminal ? 'Terminal' : titleize(status || phase || 'active'));

  if (SUCCESS_STATUSES.has(status) || terminal) {
    return { label, detail, tone: 'success', terminal };
  }
  if (DANGER_STATUSES.has(status)) {
    return { label, detail, tone: 'danger', terminal };
  }
  if (WARNING_STATUSES.has(status) || WARNING_STATUSES.has(phase)) {
    return { label, detail, tone: 'warning', terminal };
  }
  if (INFO_STATUSES.has(status) || INFO_STATUSES.has(phase)) {
    return { label, detail, tone: 'info', terminal };
  }
  return { label, detail, tone: 'neutral', terminal };
}
