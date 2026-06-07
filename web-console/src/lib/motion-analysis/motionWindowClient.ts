'use client';

import type { MotionWindowSummary } from './livePoseWindow';

export type AppendMotionWindowInput = {
  apiUrl: string;
  summary: MotionWindowSummary;
  receivedAtMs?: number;
};

export type AppendMotionWindowResponse = {
  accepted?: boolean;
  reason?: string;
  live_session_id?: string;
  motion_window_ref?: string;
  summary_count?: number;
  summary?: MotionWindowSummary;
};

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

function resolveApiBase(apiUrl: string): string {
  if (apiUrl.trim()) {
    return trimTrailingSlash(apiUrl.trim());
  }
  if (typeof window !== 'undefined') {
    return window.location.origin;
  }
  return '';
}

function buildApiUrl(apiUrl: string, path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const apiBase = resolveApiBase(apiUrl);
  return apiBase ? `${apiBase}${normalizedPath}` : normalizedPath;
}

export async function appendMotionWindow({
  apiUrl,
  summary,
  receivedAtMs,
}: AppendMotionWindowInput): Promise<AppendMotionWindowResponse> {
  const response = await fetch(
    buildApiUrl(apiUrl, '/api/v1/capabilities/motion_runtime/analysis/motion-windows'),
    {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        motion_window_summary: summary,
        received_at_ms: receivedAtMs,
      }),
    },
  );
  if (!response.ok) {
    const errorPayload = await response.json().catch(() => null);
    const detail = typeof errorPayload === 'object' && errorPayload && 'detail' in errorPayload
      ? String((errorPayload as { detail?: unknown }).detail || '')
      : '';
    throw new Error(detail || `Motion window append failed: ${response.status}`);
  }
  const payload = await response.json();
  return typeof payload === 'object' && payload !== null
    ? payload as AppendMotionWindowResponse
    : {};
}
