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

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}

function readString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function readNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

const COMPACT_GUIDANCE_METADATA_KEYS = [
  'dwpose_node_deltas',
  'sway_metrics',
  'phase_metrics',
] as const;

const COMPACT_GUIDANCE_SEVERITY_WEIGHT: Record<string, number> = {
  red: 4,
  error: 4,
  yellow: 3,
  amber: 3,
  warning: 3,
  green: 1,
  info: 1,
};

function compactGuidanceScore(record: Record<string, unknown>, index: number): number {
  const severity = readString(record.severity).toLowerCase();
  const severityScore = COMPACT_GUIDANCE_SEVERITY_WEIGHT[severity] || 0;
  const deltaScore = readNumber(record.delta_score) || 0;
  return severityScore * 10 + deltaScore - index / 1000;
}

function compactGuidanceText(record: Record<string, unknown>): string {
  const guidance = readString(record.guidance);
  const finding = readString(record.finding);
  const text = guidance || finding;
  if (!text) {
    return '';
  }
  const label = readString(record.node_label)
    || readString(record.axis)
    || readString(record.phase);
  return label ? `${label}: ${text}` : text;
}

function deriveCompactGuidanceFindings(summary: MotionWindowSummary): string[] {
  const seen = new Set<string>();
  const addUnique = (values: string[], value: string) => {
    const trimmed = value.trim();
    if (!trimmed || seen.has(trimmed)) {
      return;
    }
    seen.add(trimmed);
    values.push(trimmed);
  };
  const derived: Array<{ text: string; score: number }> = [];
  let index = 0;
  for (const key of COMPACT_GUIDANCE_METADATA_KEYS) {
    const entries = summary.metadata[key];
    if (!Array.isArray(entries)) {
      continue;
    }
    for (const entry of entries) {
      if (!isRecord(entry)) {
        continue;
      }
      const text = compactGuidanceText(entry);
      if (!text) {
        continue;
      }
      derived.push({ text, score: compactGuidanceScore(entry, index) });
      index += 1;
    }
  }
  derived.sort((left, right) => right.score - left.score);

  const findings: string[] = [];
  for (const item of derived) {
    addUnique(findings, item.text);
    if (findings.length >= 5) {
      return findings;
    }
  }
  for (const finding of summary.findings) {
    addUnique(findings, finding);
    if (findings.length >= 5) {
      break;
    }
  }
  return findings;
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
    findings: deriveCompactGuidanceFindings(summary),
    summary,
  };
}
