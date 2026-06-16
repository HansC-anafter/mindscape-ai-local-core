'use client';

import type { AddressableGraphSelection } from '@/lib/addressable-object-layer';

import {
  resolveInstructionSourceKindForProvider,
  type MotionCoachCapabilityCode,
  type MotionPracticeLessonHandoff,
} from './motionPracticeLessonHandoff';

function readString(value: unknown): string {
  return typeof value === 'string' && value.trim() ? value.trim() : '';
}

function readFiniteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function buildCourseChaptersInput(input: {
  instructionRefId: string;
  title: string;
  startSeconds: number | null;
  endSeconds: number | null;
}): string | undefined {
  if (input.startSeconds == null || input.endSeconds == null || input.endSeconds <= input.startSeconds) {
    return undefined;
  }
  return JSON.stringify([
    {
      chapter_id: input.instructionRefId,
      title: input.title,
      start_ms: Math.round(input.startSeconds * 1000),
      end_ms: Math.round(input.endSeconds * 1000),
    },
  ]);
}

export function buildMotionPracticeLessonHandoffFromGraphSelection(input: {
  capabilityCode: MotionCoachCapabilityCode;
  graphSelection: AddressableGraphSelection | null | undefined;
}): MotionPracticeLessonHandoff | null {
  const selection = input.graphSelection;
  if (!selection || selection.owner_pack !== 'social_video_refs') {
    return null;
  }
  const anchor = selection.anchors.find((candidate) => (
    candidate.owner_pack === 'social_video_refs'
      && candidate.object_kind === 'instruction_ref'
  ));
  if (!anchor) {
    return null;
  }
  const selector = anchor.selector || anchor.ref?.selector || {};
  const sourceValue = readString(selector.canonical_url);
  if (!sourceValue) {
    return null;
  }
  const sourceProvider = readString(selector.source_provider);
  const instructionRefId = readString(selector.instruction_ref_id) || anchor.object_id;
  const sourceTitle = readString(anchor.label) || readString(selector.provider_video_id) || instructionRefId;
  return {
    capabilityCode: input.capabilityCode,
    sourceKind: resolveInstructionSourceKindForProvider(sourceProvider),
    sourceValue,
    sourceTitle: sourceTitle || undefined,
    sourceProvider: sourceProvider || undefined,
    courseChaptersInput: buildCourseChaptersInput({
      instructionRefId,
      title: sourceTitle || 'Selected reference lesson',
      startSeconds: readFiniteNumber(selector.start_seconds),
      endSeconds: readFiniteNumber(selector.end_seconds),
    }),
  };
}
