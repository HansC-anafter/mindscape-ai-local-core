'use client';

import React from 'react';

import type { MotionPracticeInstructionRef } from '../motionPracticeLauncher';

export type MotionPracticeInstructionSourceKind =
  | 'local_video_smoke_ref'
  | 'youtube_instruction_ref'
  | 'manual_teacher_ref';

export type MotionPracticeInstructionSourceState = {
  kind: MotionPracticeInstructionSourceKind;
  value: string;
  courseChapters?: Record<string, unknown>[];
};

export const DEFAULT_MOTION_PRACTICE_INSTRUCTION_SOURCE: MotionPracticeInstructionSourceState = {
  kind: 'manual_teacher_ref',
  value: '',
};

const SOURCE_LABELS: Record<MotionPracticeInstructionSourceKind, string> = {
  local_video_smoke_ref: 'Local video',
  youtube_instruction_ref: 'YouTube',
  manual_teacher_ref: 'Manual ref',
};

const SOURCE_PLACEHOLDERS: Record<MotionPracticeInstructionSourceKind, string> = {
  local_video_smoke_ref: 'mindscape://motion-video-smoke/session/...',
  youtube_instruction_ref: 'https://www.youtube.com/watch?v=...',
  manual_teacher_ref: 'mindscape://yogacoach/teacher-library/...',
};

export function buildMotionPracticeInstructionRefs(
  source: MotionPracticeInstructionSourceState,
): MotionPracticeInstructionRef[] {
  const value = source.value.trim();
  const courseChapters = Array.isArray(source.courseChapters)
    ? source.courseChapters
    : [];
  if (source.kind === 'local_video_smoke_ref') {
    return [
      {
        ref_type: 'local_video_smoke_ref',
        source_provider: 'local_video',
        media_ref: value || 'mindscape://motion-video-smoke/current',
        frame_readable: false,
        motion_analysis_source: true,
        ...(courseChapters.length ? { course_chapters: courseChapters } : {}),
      },
    ];
  }
  if (!value) {
    return [];
  }
  if (source.kind === 'youtube_instruction_ref') {
    return [
      {
        ref_type: 'youtube_instruction_ref',
        source_provider: 'youtube',
        video_ref: value,
        frame_readable: false,
        motion_analysis_source: false,
        ...(courseChapters.length ? { course_chapters: courseChapters } : {}),
      },
    ];
  }
  return [
    {
      ref_type: 'manual_teacher_ref',
      source_provider: 'manual',
      teacher_ref: value,
      frame_readable: false,
      motion_analysis_source: false,
      ...(courseChapters.length ? { course_chapters: courseChapters } : {}),
    },
  ];
}

interface MotionPracticeInstructionSourcePanelProps {
  source: MotionPracticeInstructionSourceState;
  onChange: (nextSource: MotionPracticeInstructionSourceState) => void;
}

export function MotionPracticeInstructionSourcePanel({
  source,
  onChange,
}: MotionPracticeInstructionSourcePanelProps) {
  const refs = buildMotionPracticeInstructionRefs(source);
  return (
    <div className="space-y-2 rounded border border-gray-200 p-2 dark:border-gray-800">
      <label className="block">
        <span className="mb-1 block text-[11px] font-medium uppercase tracking-normal text-gray-500 dark:text-gray-400">
          Instruction source
        </span>
        <select
          value={source.kind}
          onChange={(event) => onChange({
            kind: event.target.value as MotionPracticeInstructionSourceKind,
            value: '',
            courseChapters: source.courseChapters,
          })}
          className="w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-xs text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
          data-testid="motion-practice-instruction-source-kind"
        >
          {Object.entries(SOURCE_LABELS).map(([kind, label]) => (
            <option key={kind} value={kind}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <input
        value={source.value}
        onChange={(event) => onChange({ ...source, value: event.target.value })}
        placeholder={SOURCE_PLACEHOLDERS[source.kind]}
        className="w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-xs text-gray-900 placeholder:text-gray-400 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
        data-testid="motion-practice-instruction-source-value"
      />
      <div
        className="rounded border border-gray-200 px-2 py-1 text-[11px] text-gray-600 dark:border-gray-800 dark:text-gray-300"
        data-testid="motion-practice-instruction-source-status"
      >
        {refs.length
          ? `${SOURCE_LABELS[source.kind]} ref ready`
          : 'No instruction ref selected'}
      </div>
    </div>
  );
}

export default MotionPracticeInstructionSourcePanel;
