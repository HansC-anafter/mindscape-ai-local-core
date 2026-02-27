/**
 * Unified server timestamp utilities.
 * Rule: all server timestamps are UTC. Naive strings are treated as UTC.
 */

/**
 * Parse a server timestamp (UTC or naive) into a Date.
 */
export function parseServerTimestamp(value?: string | null): Date | null {
  if (!value) return null;
  const s = value.trim();
  if (!s) return null;

  const hasTimezone = /[zZ]$|[+-]\d{2}(:\d{2})?$/.test(s);
  const normalized = hasTimezone ? s : `${s.replace(' ', 'T')}Z`;
  const d = new Date(normalized);
  return Number.isFinite(d.getTime()) ? d : null;
}

/**
 * Format timestamp as localized date-time.
 */
export function formatLocalDateTime(value?: string | null): string {
  const d = parseServerTimestamp(value);
  return d ? d.toLocaleString() : "—";
}

/**
 * Format timestamp as localized time.
 */
export function formatLocalTime(value?: string | null): string {
  const d = parseServerTimestamp(value);
  return d ? d.toLocaleTimeString() : "—";
}

/**
 * Minutes elapsed since timestamp.
 */
export function minutesAgo(value?: string | null): number | null {
  const t = parseServerTimestamp(value)?.getTime();
  if (!Number.isFinite(t)) return null;

  const diffMs = Date.now() - (t as number);
  if (!Number.isFinite(diffMs) || diffMs < 0) return null;
  return Math.floor(diffMs / 60000);
}

/**
 * Timestamp as epoch milliseconds.
 */
export function toTimestampMs(value?: string | null): number | null {
  const t = parseServerTimestamp(value)?.getTime();
  return Number.isFinite(t) ? (t as number) : null;
}
