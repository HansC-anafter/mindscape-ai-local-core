'use client';

import type {
  MotionPracticeInstructionSourceKind,
  MotionPracticeInstructionSourceState,
} from './motionPracticeInstructionSource';
import {
  buildMotionPracticeInstructionRefs,
  parseMotionPracticeCourseChaptersInput,
} from './motionPracticeInstructionSource';

export type MotionCoachCapabilityCode = 'yogacoach' | 'dance_motion_coach';

export type MotionPracticeLessonHandoff = {
  capabilityCode: MotionCoachCapabilityCode;
  sourceKind: MotionPracticeInstructionSourceKind;
  sourceValue: string;
  sourceTitle?: string;
  sourceProvider?: string;
  thumbnailUrl?: string;
  courseChaptersInput?: string;
  motionReferenceProfileArtifactId?: string;
  referenceProfileResolutionStatus?: 'resolving' | 'ready' | 'failed';
  referenceProfileResolutionError?: string;
};

const PARAM_KEYS = {
  enabled: 'motion_lesson_handoff',
  capabilityCode: 'motion_lesson_target',
  sourceKind: 'motion_lesson_kind',
  sourceValue: 'motion_lesson_value',
  sourceTitle: 'motion_lesson_title',
  sourceProvider: 'motion_lesson_provider',
  thumbnailUrl: 'motion_lesson_thumbnail',
  courseChapters: 'motion_lesson_course_chapters',
  motionReferenceProfileArtifactId: 'motion_reference_profile_artifact_id',
  handoffTarget: 'handoff_target',
  returnTo: 'return_to',
  provider: 'provider',
} as const;

function asString(value: string | null | undefined): string {
  return String(value || '').trim();
}

function isMotionCoachCapabilityCode(value: string): value is MotionCoachCapabilityCode {
  return value === 'yogacoach' || value === 'dance_motion_coach';
}

function isInstructionSourceKind(value: string): value is MotionPracticeInstructionSourceKind {
  return value === 'local_video_smoke_ref'
    || value === 'bilibili_instruction_ref'
    || value === 'youtube_instruction_ref'
    || value === 'manual_teacher_ref';
}

function buildRelativeUrl(url: URL): string {
  return `${url.pathname}${url.search}${url.hash}`;
}

function buildUrlWithBase(path: string): URL {
  return new URL(path, 'http://mindscape.local');
}

function clearLessonHandoffParams(searchParams: URLSearchParams) {
  Object.values(PARAM_KEYS).forEach((key) => {
    searchParams.delete(key);
  });
}

export function resolveInstructionSourceKindForProvider(
  sourceProvider: string | null | undefined,
): MotionPracticeInstructionSourceKind {
  const normalizedProvider = asString(sourceProvider).toLowerCase();
  if (normalizedProvider === 'youtube') {
    return 'youtube_instruction_ref';
  }
  if (normalizedProvider === 'bilibili') {
    return 'bilibili_instruction_ref';
  }
  return 'manual_teacher_ref';
}

export function buildMotionCoachReferenceLibraryHref(input: {
  workspaceId: string;
  capabilityCode: MotionCoachCapabilityCode;
  returnTo: string;
  provider?: string;
}): string {
  const url = buildUrlWithBase(
    `/workspaces/${encodeURIComponent(input.workspaceId)}/capability-ui-hosts/social_video_refs/refs`,
  );
  url.searchParams.set(PARAM_KEYS.handoffTarget, input.capabilityCode);
  url.searchParams.set(PARAM_KEYS.returnTo, input.returnTo);
  url.searchParams.set(PARAM_KEYS.provider, asString(input.provider) || 'youtube');
  return buildRelativeUrl(url);
}

export function buildMotionCoachLessonHandoffHref(input: {
  returnTo: string;
  capabilityCode: MotionCoachCapabilityCode;
  sourceKind: MotionPracticeInstructionSourceKind;
  sourceValue: string;
  sourceTitle?: string;
  sourceProvider?: string;
  thumbnailUrl?: string;
  courseChaptersInput?: string;
  motionReferenceProfileArtifactId?: string;
}): string {
  const url = buildUrlWithBase(input.returnTo);
  clearLessonHandoffParams(url.searchParams);
  url.searchParams.set(PARAM_KEYS.enabled, '1');
  url.searchParams.set(PARAM_KEYS.capabilityCode, input.capabilityCode);
  url.searchParams.set(PARAM_KEYS.sourceKind, input.sourceKind);
  url.searchParams.set(PARAM_KEYS.sourceValue, input.sourceValue.trim());
  if (asString(input.sourceTitle)) {
    url.searchParams.set(PARAM_KEYS.sourceTitle, input.sourceTitle!.trim());
  }
  if (asString(input.sourceProvider)) {
    url.searchParams.set(PARAM_KEYS.sourceProvider, input.sourceProvider!.trim());
  }
  if (asString(input.thumbnailUrl)) {
    url.searchParams.set(PARAM_KEYS.thumbnailUrl, input.thumbnailUrl!.trim());
  }
  if (asString(input.courseChaptersInput)) {
    url.searchParams.set(PARAM_KEYS.courseChapters, input.courseChaptersInput!.trim());
  }
  if (asString(input.motionReferenceProfileArtifactId)) {
    url.searchParams.set(
      PARAM_KEYS.motionReferenceProfileArtifactId,
      input.motionReferenceProfileArtifactId!.trim(),
    );
  }
  return buildRelativeUrl(url);
}

export function parseMotionPracticeLessonHandoff(
  searchParams: URLSearchParams | Pick<URLSearchParams, 'get'> | null | undefined,
): MotionPracticeLessonHandoff | null {
  if (!searchParams) {
    return null;
  }
  const enabled = asString(searchParams.get(PARAM_KEYS.enabled));
  const capabilityCode = asString(searchParams.get(PARAM_KEYS.capabilityCode));
  const sourceKind = asString(searchParams.get(PARAM_KEYS.sourceKind));
  const sourceValue = asString(searchParams.get(PARAM_KEYS.sourceValue));
  if (enabled !== '1' || !isMotionCoachCapabilityCode(capabilityCode) || !isInstructionSourceKind(sourceKind) || !sourceValue) {
    return null;
  }
  const sourceTitle = asString(searchParams.get(PARAM_KEYS.sourceTitle));
  const sourceProvider = asString(searchParams.get(PARAM_KEYS.sourceProvider));
  const thumbnailUrl = asString(searchParams.get(PARAM_KEYS.thumbnailUrl));
  const courseChaptersInput = asString(searchParams.get(PARAM_KEYS.courseChapters));
  const motionReferenceProfileArtifactId = asString(
    searchParams.get(PARAM_KEYS.motionReferenceProfileArtifactId),
  );
  return {
    capabilityCode,
    sourceKind,
    sourceValue,
    sourceTitle: sourceTitle || undefined,
    sourceProvider: sourceProvider || undefined,
    thumbnailUrl: thumbnailUrl || undefined,
    courseChaptersInput: courseChaptersInput || undefined,
    motionReferenceProfileArtifactId: motionReferenceProfileArtifactId || undefined,
  };
}

export function buildInstructionSourceStateFromLessonHandoff(
  handoff: MotionPracticeLessonHandoff | null | undefined,
): MotionPracticeInstructionSourceState | null {
  if (!handoff) {
    return null;
  }
  const courseChaptersInput = handoff.courseChaptersInput || '';
  const parseResult = parseMotionPracticeCourseChaptersInput(courseChaptersInput);
  const resolutionError = handoff.referenceProfileResolutionStatus === 'resolving'
    ? 'Reference motion profile is still resolving.'
    : handoff.referenceProfileResolutionStatus === 'failed'
      ? handoff.referenceProfileResolutionError || 'Reference motion profile resolution failed.'
      : null;
  return {
    kind: handoff.sourceKind,
    value: handoff.sourceValue,
    courseChaptersInput,
    courseChapters: parseResult.courseChapters,
    courseChaptersError: resolutionError || parseResult.error,
    motionReferenceProfileArtifactId: handoff.motionReferenceProfileArtifactId,
  };
}

export function buildInstructionRefsFromLessonHandoff(
  handoff: MotionPracticeLessonHandoff | null | undefined,
): Record<string, unknown>[] {
  const sourceState = buildInstructionSourceStateFromLessonHandoff(handoff);
  if (!sourceState) {
    return [];
  }
  return buildMotionPracticeInstructionRefs(sourceState);
}

export function readMotionCoachHandoffTarget(
  searchParams: URLSearchParams | Pick<URLSearchParams, 'get'> | null | undefined,
): MotionCoachCapabilityCode | null {
  const target = asString(searchParams?.get(PARAM_KEYS.handoffTarget));
  return isMotionCoachCapabilityCode(target) ? target : null;
}

export function readMotionCoachHandoffReturnTo(
  searchParams: URLSearchParams | Pick<URLSearchParams, 'get'> | null | undefined,
): string | null {
  const returnTo = asString(searchParams?.get(PARAM_KEYS.returnTo));
  return returnTo || null;
}

export function readMotionCoachPreferredProvider(
  searchParams: URLSearchParams | Pick<URLSearchParams, 'get'> | null | undefined,
): string | null {
  const provider = asString(searchParams?.get(PARAM_KEYS.provider));
  return provider || null;
}
