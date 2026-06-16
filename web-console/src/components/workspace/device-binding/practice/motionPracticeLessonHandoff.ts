'use client';

import type {
  MotionPracticeInstructionSourceKind,
  MotionPracticeInstructionSourceState,
} from './MotionPracticeInstructionSourcePanel';
import {
  buildMotionPracticeInstructionRefs,
  parseMotionPracticeCourseChaptersInput,
} from './MotionPracticeInstructionSourcePanel';

export type MotionCoachCapabilityCode = 'yogacoach' | 'dance_motion_coach';

export type MotionPracticeLessonHandoff = {
  capabilityCode: MotionCoachCapabilityCode;
  sourceKind: MotionPracticeInstructionSourceKind;
  sourceValue: string;
  sourceTitle?: string;
  sourceProvider?: string;
  courseChaptersInput?: string;
};

const PARAM_KEYS = {
  enabled: 'motion_lesson_handoff',
  capabilityCode: 'motion_lesson_target',
  sourceKind: 'motion_lesson_kind',
  sourceValue: 'motion_lesson_value',
  sourceTitle: 'motion_lesson_title',
  sourceProvider: 'motion_lesson_provider',
  courseChapters: 'motion_lesson_course_chapters',
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
  return asString(sourceProvider).toLowerCase() === 'youtube'
    ? 'youtube_instruction_ref'
    : 'manual_teacher_ref';
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
  courseChaptersInput?: string;
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
  if (asString(input.courseChaptersInput)) {
    url.searchParams.set(PARAM_KEYS.courseChapters, input.courseChaptersInput!.trim());
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
  const courseChaptersInput = asString(searchParams.get(PARAM_KEYS.courseChapters));
  return {
    capabilityCode,
    sourceKind,
    sourceValue,
    sourceTitle: sourceTitle || undefined,
    sourceProvider: sourceProvider || undefined,
    courseChaptersInput: courseChaptersInput || undefined,
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
  return {
    kind: handoff.sourceKind,
    value: handoff.sourceValue,
    courseChaptersInput,
    courseChapters: parseResult.courseChapters,
    courseChaptersError: parseResult.error,
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
