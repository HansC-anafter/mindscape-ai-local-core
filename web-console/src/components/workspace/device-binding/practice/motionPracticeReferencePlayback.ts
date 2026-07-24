import type { AOLMeetingClientAction } from '@/lib/meeting-voice/meetingClientActionEvent';

import type { MotionPracticeLessonHandoff } from './motionPracticeLessonHandoff';

export type MotionPracticeReferencePlaybackStatus =
  | 'awaiting_confirmation'
  | 'countdown'
  | 'starting'
  | 'playing'
  | 'complete'
  | 'failed';

export type MotionPracticeReferencePlaybackPlan = {
  schemaVersion: 'motion_practice.reference_playback.v1';
  workspaceId: string;
  meetingId: string;
  prepareActionId: string;
  confirmationActionId?: string;
  status: MotionPracticeReferencePlaybackStatus;
  reference: {
    ownerPack: string;
    objectKind: string;
    provider: string;
    providerVideoId: string;
    sourceKind: MotionPracticeLessonHandoff['sourceKind'];
    sourceUrl: string;
    title: string;
  };
  playback: {
    startMs: number;
    durationMs: number;
    loop: false;
  };
  countdownRemaining: number;
  startedAt?: string;
  error?: string;
};

export const YOGACOACH_PREPARE_REFERENCE_ACTION = 'yogacoach.prepare_reference_practice';
export const YOGACOACH_CONFIRM_REFERENCE_ACTION = 'yogacoach.confirm_reference_practice';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function boundedInteger(value: unknown, fallback: number, min: number, max: number): number {
  const numeric = typeof value === 'number' && Number.isFinite(value) ? Math.round(value) : fallback;
  return Math.min(max, Math.max(min, numeric));
}

function isInstructionSourceKind(value: string): value is MotionPracticeLessonHandoff['sourceKind'] {
  return value === 'local_video_smoke_ref'
    || value === 'bilibili_instruction_ref'
    || value === 'youtube_instruction_ref'
    || value === 'manual_teacher_ref';
}

export function prepareMotionPracticeReferencePlayback(
  action: AOLMeetingClientAction,
): { handoff: MotionPracticeLessonHandoff; plan: MotionPracticeReferencePlaybackPlan } | null {
  if (
    action.packCode !== 'yogacoach'
    || action.actionCode !== YOGACOACH_PREPARE_REFERENCE_ACTION
  ) {
    return null;
  }
  const reference = isRecord(action.payload.reference) ? action.payload.reference : null;
  const playback = isRecord(action.payload.playback) ? action.payload.playback : null;
  const sourceKind = readString(reference?.source_kind);
  const sourceUrl = readString(reference?.source_url);
  const title = readString(reference?.title);
  if (!reference || !playback || !isInstructionSourceKind(sourceKind) || !sourceUrl || !title) {
    return null;
  }
  const plan: MotionPracticeReferencePlaybackPlan = {
    schemaVersion: 'motion_practice.reference_playback.v1',
    workspaceId: action.workspaceId,
    meetingId: action.meetingId,
    prepareActionId: action.actionId,
    status: 'awaiting_confirmation',
    reference: {
      ownerPack: readString(reference.owner_pack) || 'social_video_refs',
      objectKind: readString(reference.object_kind) || 'instruction_ref',
      provider: readString(reference.provider),
      providerVideoId: readString(reference.provider_video_id),
      sourceKind,
      sourceUrl,
      title,
    },
    playback: {
      startMs: boundedInteger(playback.start_ms, 0, 0, 86_400_000),
      durationMs: boundedInteger(playback.duration_ms, 1_800_000, 60_000, 14_400_000),
      loop: false,
    },
    countdownRemaining: 0,
  };
  return {
    handoff: {
      capabilityCode: 'yogacoach',
      sourceKind,
      sourceValue: sourceUrl,
      sourceTitle: title,
      sourceProvider: plan.reference.provider,
    },
    plan,
  };
}

export function confirmMotionPracticeReferencePlayback(
  current: MotionPracticeReferencePlaybackPlan | null,
  action: AOLMeetingClientAction,
): MotionPracticeReferencePlaybackPlan | null {
  if (
    !current
    || action.packCode !== 'yogacoach'
    || action.actionCode !== YOGACOACH_CONFIRM_REFERENCE_ACTION
    || action.workspaceId !== current.workspaceId
    || action.meetingId !== current.meetingId
    || current.status !== 'awaiting_confirmation'
  ) {
    return null;
  }
  return {
    ...current,
    confirmationActionId: action.actionId,
    status: 'countdown',
    countdownRemaining: boundedInteger(action.payload.countdown_seconds, 5, 1, 15),
    error: undefined,
  };
}

export function buildReferencePlaybackEmbedUrl(
  plan: MotionPracticeReferencePlaybackPlan,
): string {
  if (plan.reference.provider.toLowerCase() === 'bilibili' && plan.reference.providerVideoId) {
    const url = new URL('https://player.bilibili.com/player.html');
    url.searchParams.set('bvid', plan.reference.providerVideoId);
    url.searchParams.set('autoplay', '1');
    url.searchParams.set('high_quality', '1');
    url.searchParams.set('danmaku', '0');
    url.searchParams.set('t', String(Math.floor(plan.playback.startMs / 1000)));
    return url.toString();
  }
  return plan.reference.sourceUrl;
}
