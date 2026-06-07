'use client';

import type { MotionWindowSummary } from '@/lib/motion-analysis/livePoseWindow';

export type MotionGuidanceClientMessage =
  | {
      type: 'session_start';
      event_id?: string;
      live_session_id?: string | null;
    }
  | {
      type: 'motion_window';
      event_id?: string;
      live_session_id?: string | null;
      motion_window_ref?: string | null;
      confidence?: number | null;
      top_findings?: string[];
      findings?: string[];
      metadata?: Record<string, unknown>;
    }
  | {
      type: 'interrupt' | 'ack' | 'session_close';
      event_id?: string;
    };

export type MotionGuidanceEvent = {
  type:
    | 'session_ready'
    | 'guidance_cue'
    | 'guidance_suppressed'
    | 'interrupted'
    | 'session_closed'
    | 'session_error';
  workspace_id: string;
  meeting_id: string;
  practice_session_id: string;
  state?: 'idle' | 'active' | 'interrupted' | 'closed';
  event_id?: string;
  cue_id?: string;
  cue_key?: string;
  cue_text?: string;
  cue_priority?: 'info' | 'warning' | 'correction';
  speakable?: boolean;
  motion_window_ref?: string;
  rollup_ref?: string;
  command_ref?: string;
  reason?: string;
  message?: string;
  recoverable?: boolean;
  throttle_until_epoch?: number;
};

export type MotionGuidanceWindowEvent = {
  eventId: string;
  liveSessionId: string;
  motionWindowRef: string;
  confidence: number | null;
  findings: string[];
  summary: MotionWindowSummary;
};

export type MotionGuidanceSocket = {
  raw: WebSocket;
  send: (message: MotionGuidanceClientMessage) => void;
  close: () => void;
};

type OpenMotionGuidanceSocketInput = {
  apiBase: string;
  workspaceId: string;
  meetingId: string;
  practiceSessionId: string;
  liveSessionId?: string | null;
  onOpen?: () => void;
  onEvent?: (event: MotionGuidanceEvent) => void;
  onError?: (error: Error) => void;
  onClose?: () => void;
};

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

function getBrowserOrigin(): string {
  if (typeof window === 'undefined') {
    return 'http://localhost:8300';
  }
  return window.location.origin;
}

function resolveHttpBase(apiBase: string): string {
  return trimTrailingSlash(apiBase || getBrowserOrigin()) || getBrowserOrigin();
}

export function buildMotionGuidanceWebSocketUrl({
  apiBase,
  workspaceId,
  meetingId,
  practiceSessionId,
}: {
  apiBase: string;
  workspaceId: string;
  meetingId: string;
  practiceSessionId: string;
}): string {
  const base = resolveHttpBase(apiBase);
  const url = new URL(base, getBrowserOrigin());
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.pathname = `/api/v1/workspaces/${encodeURIComponent(workspaceId)}/meetings/${encodeURIComponent(meetingId)}/motion-guidance/${encodeURIComponent(practiceSessionId)}/stream`;
  url.search = '';
  return url.toString();
}

export function openMotionGuidanceSocket(
  input: OpenMotionGuidanceSocketInput,
): MotionGuidanceSocket {
  const socket = new WebSocket(buildMotionGuidanceWebSocketUrl(input));
  const send = (message: MotionGuidanceClientMessage) => {
    if (socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(message));
    }
  };
  socket.onopen = () => {
    input.onOpen?.();
    send({
      type: 'session_start',
      event_id: `${input.practiceSessionId}:session_start`,
      live_session_id: input.liveSessionId,
    });
  };
  socket.onmessage = (message) => {
    try {
      input.onEvent?.(JSON.parse(String(message.data)) as MotionGuidanceEvent);
    } catch (error) {
      input.onError?.(error instanceof Error ? error : new Error('invalid_motion_guidance_event'));
    }
  };
  socket.onerror = () => input.onError?.(new Error('motion_guidance_socket_error'));
  socket.onclose = () => input.onClose?.();
  return {
    raw: socket,
    send,
    close: () => socket.close(),
  };
}

export function buildMotionGuidanceWindowEvent({
  liveSessionId,
  motionWindowRef,
  summary,
}: {
  liveSessionId: string;
  motionWindowRef: string;
  summary: MotionWindowSummary;
}): MotionGuidanceWindowEvent {
  const meanConfidence = summary.confidence_stats.mean_confidence;
  return {
    eventId: `${summary.window_id}:guidance`,
    liveSessionId,
    motionWindowRef,
    confidence: typeof meanConfidence === 'number' ? meanConfidence : null,
    findings: summary.findings,
    summary,
  };
}
