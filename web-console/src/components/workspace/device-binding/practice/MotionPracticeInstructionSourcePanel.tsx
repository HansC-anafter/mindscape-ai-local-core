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
  courseChaptersInput?: string;
  courseChaptersError?: string | null;
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

export type MotionPracticeCourseChaptersParseResult = {
  courseChapters: Record<string, unknown>[];
  error: string | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function readText(
  chapter: Record<string, unknown>,
  keys: string[],
): string {
  for (const key of keys) {
    const value = chapter[key];
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }
  return '';
}

function readTimeMs(
  chapter: Record<string, unknown>,
  millisecondKey: string,
  secondKey: string,
): number | null {
  const millisecondValue = chapter[millisecondKey];
  const secondValue = chapter[secondKey];
  const hasMillisecondValue =
    typeof millisecondValue === 'number' || typeof millisecondValue === 'string';
  const rawValue = hasMillisecondValue
    ? millisecondValue
    : secondValue;
  const numericValue = typeof rawValue === 'string' ? Number(rawValue.trim()) : rawValue;
  if (typeof numericValue !== 'number' || !Number.isFinite(numericValue)) {
    return null;
  }
  return hasMillisecondValue ? Math.round(numericValue) : Math.round(numericValue * 1000);
}

export function parseMotionPracticeCourseChaptersInput(
  input: string | undefined,
): MotionPracticeCourseChaptersParseResult {
  const trimmedInput = (input || '').trim();
  if (!trimmedInput) {
    return { courseChapters: [], error: null };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmedInput);
  } catch {
    return {
      courseChapters: [],
      error: 'Course chapters must be a valid JSON array.',
    };
  }

  if (!Array.isArray(parsed)) {
    return {
      courseChapters: [],
      error: 'Course chapters must be a JSON array.',
    };
  }

  const courseChapters: Record<string, unknown>[] = [];
  for (const [index, rawChapter] of parsed.entries()) {
    if (!isRecord(rawChapter)) {
      return {
        courseChapters: [],
        error: `Chapter ${index + 1} must be an object.`,
      };
    }
    const chapterId = readText(rawChapter, ['chapter_id', 'id']);
    const title = readText(rawChapter, ['title', 'display_label', 'label']);
    const startMs = readTimeMs(rawChapter, 'start_ms', 'start_time');
    const endMs = readTimeMs(rawChapter, 'end_ms', 'end_time');
    if (!chapterId) {
      return {
        courseChapters: [],
        error: `Chapter ${index + 1} is missing chapter_id or id.`,
      };
    }
    if (!title) {
      return {
        courseChapters: [],
        error: `Chapter ${index + 1} is missing title, display_label, or label.`,
      };
    }
    if (startMs === null || endMs === null) {
      return {
        courseChapters: [],
        error: `Chapter ${index + 1} is missing start/end time.`,
      };
    }
    if (endMs < startMs) {
      return {
        courseChapters: [],
        error: `Chapter ${index + 1} end time must not be before start time.`,
      };
    }
    courseChapters.push({
      ...rawChapter,
      chapter_id: chapterId,
      title,
      start_ms: startMs,
      end_ms: endMs,
    });
  }

  return { courseChapters, error: null };
}

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

export default MotionPracticeInstructionSourcePanel;
