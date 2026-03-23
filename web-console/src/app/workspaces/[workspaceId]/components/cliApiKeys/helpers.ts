'use client';

import { parseServerTimestamp } from '@/lib/time';

export function formatServerDateTime(value: string | null): string {
  const parsed = parseServerTimestamp(value);
  if (!parsed) {
    return 'Unknown';
  }

  return parsed.toLocaleString([], {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatTimeRemaining(value: string | null): string | null {
  const parsed = parseServerTimestamp(value);
  if (!parsed) {
    return null;
  }

  const diffMs = parsed.getTime() - Date.now();
  if (diffMs <= 0) {
    return 'ready now';
  }

  const totalMinutes = Math.ceil(diffMs / 60000);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;

  if (hours > 0 && minutes > 0) {
    return `in ${hours}h ${minutes}m`;
  }
  if (hours > 0) {
    return `in ${hours}h`;
  }

  return `in ${minutes}m`;
}
