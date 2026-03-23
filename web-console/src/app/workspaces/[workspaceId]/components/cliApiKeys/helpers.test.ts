import { describe, expect, it, vi } from 'vitest';

import { formatTimeRemaining } from './helpers';

describe('cliApiKeys helpers', () => {
  it('formats remaining time in minutes and hours', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-03-24T00:00:00Z'));

    expect(formatTimeRemaining('2026-03-24T00:10:00Z')).toBe('in 10m');
    expect(formatTimeRemaining('2026-03-24T02:00:00Z')).toBe('in 2h');
    expect(formatTimeRemaining('2026-03-24T02:15:00Z')).toBe('in 2h 15m');
    expect(formatTimeRemaining('2026-03-23T23:59:00Z')).toBe('ready now');

    vi.useRealTimers();
  });
});
