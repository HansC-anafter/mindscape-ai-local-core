import type { MotionPracticeInstructionRef } from '../motionPracticeLauncher';

export type MotionPracticeInstructionSourceKind =
  | 'local_video_smoke_ref'
  | 'bilibili_instruction_ref'
  | 'youtube_instruction_ref'
  | 'manual_teacher_ref';

export type MotionPracticeInstructionSourceState = {
  kind: MotionPracticeInstructionSourceKind;
  value: string;
  courseChapters?: Record<string, unknown>[];
  courseChaptersInput?: string;
  courseChaptersError?: string | null;
  motionReferenceProfileArtifactId?: string;
};

export type MotionPracticeReferenceSegmentType =
  | 'practice'
  | 'demo'
  | 'asana'
  | 'flow'
  | 'instruction'
  | 'rest'
  | 'chat'
  | 'transition'
  | 'unknown';

const SCOREABLE_SEGMENT_TYPES = new Set<MotionPracticeReferenceSegmentType>([
  'practice',
  'demo',
  'asana',
  'flow',
]);

const NON_SCOREABLE_TITLE_HINTS: Array<[RegExp, MotionPracticeReferenceSegmentType]> = [
  [/\b(rest|break|pause|relax|savasana)\b/i, 'rest'],
  [/\b(chat|q\s*&\s*a|qa|talk|intro|outro)\b/i, 'chat'],
  [/\b(instruction|explain|explanation|lecture|teach|cue)\b/i, 'instruction'],
  [/\b(transition|setup|prepare)\b/i, 'transition'],
  [/(休息|放鬆|停留|大休息)/, 'rest'],
  [/(聊天|問答|閒聊|開場|結尾)/, 'chat'],
  [/(講解|說明|教學|提示)/, 'instruction'],
  [/(轉場|準備)/, 'transition'],
];

const SCOREABLE_TITLE_HINTS: Array<[RegExp, MotionPracticeReferenceSegmentType]> = [
  [/\b(practice|drill|sequence|flow|vinyasa)\b/i, 'practice'],
  [/\b(demo|demonstration)\b/i, 'demo'],
  [/\b(asana|pose|posture)\b/i, 'asana'],
  [/(練習|串聯|流動|體式|姿勢|示範|演示)/, 'practice'],
];

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

function normalizeSegmentType(
  value: unknown,
  title: string,
): MotionPracticeReferenceSegmentType {
  if (typeof value === 'string' && value.trim()) {
    const normalized = value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_');
    if (SCOREABLE_SEGMENT_TYPES.has(normalized as MotionPracticeReferenceSegmentType)) {
      return normalized as MotionPracticeReferenceSegmentType;
    }
    if (['instruction', 'rest', 'chat', 'transition'].includes(normalized)) {
      return normalized as MotionPracticeReferenceSegmentType;
    }
  }
  for (const [pattern, segmentType] of NON_SCOREABLE_TITLE_HINTS) {
    if (pattern.test(title)) {
      return segmentType;
    }
  }
  for (const [pattern, segmentType] of SCOREABLE_TITLE_HINTS) {
    if (pattern.test(title)) {
      return segmentType;
    }
  }
  return 'unknown';
}

function readScoreable(
  chapter: Record<string, unknown>,
  segmentType: MotionPracticeReferenceSegmentType,
): boolean {
  if (typeof chapter.scoreable === 'boolean') {
    return chapter.scoreable;
  }
  if (typeof chapter.comparison_mode === 'string') {
    const normalized = chapter.comparison_mode.trim().toLowerCase();
    if (['context', 'ignore', 'suppress', 'non_scoreable'].includes(normalized)) {
      return false;
    }
    if (['score', 'scoreable', 'motion', 'compare'].includes(normalized)) {
      return true;
    }
  }
  return segmentType === 'unknown' || SCOREABLE_SEGMENT_TYPES.has(segmentType);
}

function buildSegmentGraph(
  chapters: Record<string, unknown>[],
): Record<string, unknown> {
  return {
    graph_version: 'motion_reference_segment_graph.v1',
    ordered_edges: chapters.slice(0, -1).map((chapter, index) => ({
      from: chapter.chapter_id,
      to: chapters[index + 1].chapter_id,
      relation: 'next',
    })),
    scoreable_segment_ids: chapters
      .filter((chapter) => chapter.scoreable === true)
      .map((chapter) => chapter.chapter_id),
    unordered_match_enabled: true,
    resync_policy: {
      ordered_prior_enabled: true,
      unordered_fallback_enabled: true,
      skip_non_scoreable_segments: true,
    },
  };
}

function normalizeCourseChapter(
  chapter: Record<string, unknown>,
): Record<string, unknown> {
  const chapterId = readText(chapter, ['chapter_id', 'id']) || String(chapter.chapter_id || '');
  const title = readText(chapter, ['title', 'display_label', 'label']) || String(chapter.title || '');
  const startMs = readTimeMs(chapter, 'start_ms', 'start_time');
  const endMs = readTimeMs(chapter, 'end_ms', 'end_time');
  const segmentType = normalizeSegmentType(chapter.segment_type, title);
  const scoreable = readScoreable(chapter, segmentType);
  return {
    ...chapter,
    ...(chapterId ? { chapter_id: chapterId } : {}),
    ...(title ? { title } : {}),
    ...(startMs !== null ? { start_ms: startMs } : {}),
    ...(endMs !== null ? { end_ms: endMs } : {}),
    segment_type: segmentType,
    scoreable,
    match_role: scoreable ? 'instruction' : 'context',
    guidance_mode: scoreable ? 'score' : 'suppress',
  };
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
    courseChapters.push(normalizeCourseChapter({
      ...rawChapter,
      chapter_id: chapterId,
      title,
      start_ms: startMs,
      end_ms: endMs,
    }));
  }

  return { courseChapters, error: null };
}

function buildCourseMetadata(courseChapters: Record<string, unknown>[]) {
  if (!courseChapters.length) {
    return {};
  }
  const normalizedCourseChapters = courseChapters
    .filter(isRecord)
    .map((chapter) => normalizeCourseChapter(chapter));
  return {
    course_chapters: normalizedCourseChapters,
    segment_graph: buildSegmentGraph(normalizedCourseChapters),
  };
}

function buildReferenceProfileMetadata(source: MotionPracticeInstructionSourceState) {
  const artifactId = source.motionReferenceProfileArtifactId?.trim();
  return artifactId
    ? { motion_reference_profile_artifact_id: artifactId }
    : {};
}

export function buildMotionPracticeInstructionRefs(
  source: MotionPracticeInstructionSourceState,
): MotionPracticeInstructionRef[] {
  const value = source.value.trim();
  const courseChapters = Array.isArray(source.courseChapters)
    ? source.courseChapters
    : [];
  const courseMetadata = buildCourseMetadata(courseChapters);
  const referenceProfileMetadata = buildReferenceProfileMetadata(source);
  if (source.kind === 'local_video_smoke_ref') {
    return [
      {
        ref_type: 'local_video_smoke_ref',
        source_provider: 'local_video',
        media_ref: value || 'mindscape://motion-video-smoke/current',
        frame_readable: false,
        motion_analysis_source: true,
        ...referenceProfileMetadata,
        ...courseMetadata,
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
        ...referenceProfileMetadata,
        ...courseMetadata,
      },
    ];
  }
  if (source.kind === 'bilibili_instruction_ref') {
    return [
      {
        ref_type: 'video_instruction_ref',
        source_provider: 'bilibili',
        video_ref: value,
        frame_readable: false,
        motion_analysis_source: false,
        ...referenceProfileMetadata,
        ...courseMetadata,
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
      ...referenceProfileMetadata,
      ...courseMetadata,
    },
  ];
}
