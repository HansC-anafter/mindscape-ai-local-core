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
