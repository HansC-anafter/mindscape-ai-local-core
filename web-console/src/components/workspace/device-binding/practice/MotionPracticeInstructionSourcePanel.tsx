'use client';

import React from 'react';

import {
  buildMotionPracticeInstructionRefs,
  parseMotionPracticeCourseChaptersInput,
  type MotionPracticeInstructionSourceKind,
  type MotionPracticeInstructionSourceState,
} from './motionPracticeInstructionSource';

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

interface MotionPracticeInstructionSourcePanelProps {
  source: MotionPracticeInstructionSourceState;
  onChange: (nextSource: MotionPracticeInstructionSourceState) => void;
}

export function MotionPracticeInstructionSourcePanel({
  source,
  onChange,
}: MotionPracticeInstructionSourcePanelProps) {
  const refs = buildMotionPracticeInstructionRefs(source);
  const courseChapterCount = source.courseChapters?.length || 0;
  const updateCourseChaptersInput = (nextInput: string) => {
    const parseResult = parseMotionPracticeCourseChaptersInput(nextInput);
    onChange({
      ...source,
      courseChaptersInput: nextInput,
      courseChapters: parseResult.courseChapters,
      courseChaptersError: parseResult.error,
    });
  };
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
            courseChaptersInput: source.courseChaptersInput,
            courseChaptersError: source.courseChaptersError,
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
      <label className="block">
        <span className="mb-1 block text-[11px] font-medium uppercase tracking-normal text-gray-500 dark:text-gray-400">
          Materialized chapters JSON
        </span>
        <textarea
          value={source.courseChaptersInput || ''}
          onChange={(event) => updateCourseChaptersInput(event.target.value)}
          placeholder='[{"chapter_id":"chapter_1","title":"Warmup","start_ms":0,"end_ms":5000}]'
          rows={3}
          className="w-full resize-y rounded-md border border-gray-300 bg-white px-2 py-1.5 text-xs text-gray-900 placeholder:text-gray-400 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
          data-testid="motion-practice-course-chapters-input"
        />
      </label>
      <div
        className={`rounded border px-2 py-1 text-[11px] ${
          source.courseChaptersError
            ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200'
            : 'border-gray-200 text-gray-600 dark:border-gray-800 dark:text-gray-300'
        }`}
        data-testid="motion-practice-instruction-source-status"
      >
        {source.courseChaptersError
          ? source.courseChaptersError
          : refs.length
            ? `${SOURCE_LABELS[source.kind]} ref ready${courseChapterCount ? ` · ${courseChapterCount} materialized chapters` : ''}`
            : 'No instruction ref selected'}
      </div>
    </div>
  );
}

export {
  DEFAULT_MOTION_PRACTICE_INSTRUCTION_SOURCE,
  buildMotionPracticeInstructionRefs,
  parseMotionPracticeCourseChaptersInput,
  type MotionPracticeCourseChaptersParseResult,
  type MotionPracticeInstructionSourceKind,
  type MotionPracticeInstructionSourceState,
} from './motionPracticeInstructionSource';

export default MotionPracticeInstructionSourcePanel;
