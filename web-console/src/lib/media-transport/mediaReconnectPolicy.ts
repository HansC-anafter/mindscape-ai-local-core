export const MEDIA_RECONNECT_DELAYS_MS = [1500, 5000, 15000] as const;

export function hasMediaReconnectBudget(attemptCount: number): boolean {
  return attemptCount < MEDIA_RECONNECT_DELAYS_MS.length;
}

export function getMediaReconnectDelayMs(attemptCount: number): number {
  return MEDIA_RECONNECT_DELAYS_MS[
    Math.min(Math.max(attemptCount, 0), MEDIA_RECONNECT_DELAYS_MS.length - 1)
  ];
}
