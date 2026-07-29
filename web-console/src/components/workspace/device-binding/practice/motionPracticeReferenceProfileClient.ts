import type { MotionCoachCapabilityCode } from './motionPracticeLessonHandoff';

export type MotionPracticeReferenceProfileChapter = {
  chapter_id: string;
  title: string;
  start_ms: number;
  end_ms: number;
  segment_type: string;
  confidence: number | null;
};

export type MotionPracticeReferenceProfileSelection = {
  status: 'ready';
  artifact_id: string;
  reference_profile_id: string;
  source_ref: string;
  chapter_count: number;
  duration_ms: number;
  chapters: MotionPracticeReferenceProfileChapter[];
};

export class MotionPracticeReferenceProfileClientError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, status: number) {
    super(code);
    this.name = 'MotionPracticeReferenceProfileClientError';
    this.code = code;
    this.status = status;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readRequiredText(value: unknown, code: string): string {
  if (typeof value !== 'string' || !value.trim()) {
    throw new MotionPracticeReferenceProfileClientError(code, 502);
  }
  return value.trim();
}

function readBoundedInteger(
  value: unknown,
  min: number,
  max: number,
  code: string,
): number {
  if (
    typeof value !== 'number'
    || !Number.isInteger(value)
    || value < min
    || value > max
  ) {
    throw new MotionPracticeReferenceProfileClientError(code, 502);
  }
  return value;
}

function parseChapter(value: unknown): MotionPracticeReferenceProfileChapter {
  if (!isRecord(value)) {
    throw new MotionPracticeReferenceProfileClientError(
      'motion_reference_profile_chapter_invalid',
      502,
    );
  }
  const startMs = readBoundedInteger(
    value.start_ms,
    0,
    86_400_000,
    'motion_reference_profile_chapter_time_invalid',
  );
  const endMs = readBoundedInteger(
    value.end_ms,
    1,
    86_400_000,
    'motion_reference_profile_chapter_time_invalid',
  );
  if (endMs <= startMs) {
    throw new MotionPracticeReferenceProfileClientError(
      'motion_reference_profile_chapter_time_invalid',
      502,
    );
  }
  const confidence = value.confidence;
  if (
    confidence !== null
    && (
      typeof confidence !== 'number'
      || !Number.isFinite(confidence)
    )
  ) {
    throw new MotionPracticeReferenceProfileClientError(
      'motion_reference_profile_chapter_confidence_invalid',
      502,
    );
  }
  return {
    chapter_id: readRequiredText(
      value.chapter_id,
      'motion_reference_profile_chapter_id_missing',
    ),
    title: readRequiredText(
      value.title,
      'motion_reference_profile_chapter_title_missing',
    ),
    start_ms: startMs,
    end_ms: endMs,
    segment_type: readRequiredText(
      value.segment_type,
      'motion_reference_profile_chapter_segment_type_missing',
    ),
    confidence: confidence as number | null,
  };
}

export function parseMotionPracticeReferenceProfileSelection(
  value: unknown,
): MotionPracticeReferenceProfileSelection {
  if (!isRecord(value) || value.status !== 'ready') {
    throw new MotionPracticeReferenceProfileClientError(
      'motion_reference_profile_response_invalid',
      502,
    );
  }
  if (!Array.isArray(value.chapters) || value.chapters.length < 1 || value.chapters.length > 128) {
    throw new MotionPracticeReferenceProfileClientError(
      'motion_reference_profile_chapter_count_invalid',
      502,
    );
  }
  const chapters = value.chapters.map(parseChapter);
  const chapterCount = readBoundedInteger(
    value.chapter_count,
    1,
    128,
    'motion_reference_profile_chapter_count_invalid',
  );
  if (chapterCount !== chapters.length) {
    throw new MotionPracticeReferenceProfileClientError(
      'motion_reference_profile_chapter_count_mismatch',
      502,
    );
  }
  const durationMs = readBoundedInteger(
    value.duration_ms,
    1,
    86_400_000,
    'motion_reference_profile_duration_invalid',
  );
  if (durationMs !== Math.max(...chapters.map((chapter) => chapter.end_ms))) {
    throw new MotionPracticeReferenceProfileClientError(
      'motion_reference_profile_duration_mismatch',
      502,
    );
  }
  return {
    status: 'ready',
    artifact_id: readRequiredText(
      value.artifact_id,
      'motion_reference_profile_artifact_id_missing',
    ),
    reference_profile_id: readRequiredText(
      value.reference_profile_id,
      'motion_reference_profile_id_missing',
    ),
    source_ref: readRequiredText(
      value.source_ref,
      'motion_reference_profile_source_ref_missing',
    ),
    chapter_count: chapterCount,
    duration_ms: durationMs,
    chapters,
  };
}

function resolveApiBase(apiUrl: string): string {
  const explicit = apiUrl.trim().replace(/\/+$/, '');
  if (explicit) {
    return explicit;
  }
  return typeof window === 'undefined' ? '' : window.location.origin;
}

export async function fetchMotionPracticeReferenceProfileSelection(input: {
  apiUrl: string;
  workspaceId: string;
  capabilityCode: MotionCoachCapabilityCode;
  sourceRef: string;
  artifactId?: string;
  fetchImpl?: typeof fetch;
}): Promise<MotionPracticeReferenceProfileSelection> {
  const apiBase = resolveApiBase(input.apiUrl);
  const path = `/api/v1/workspaces/${encodeURIComponent(input.workspaceId)}/motion-reference-profiles/selection`;
  const url = new URL(`${apiBase}${path}`, apiBase || 'http://mindscape.local');
  url.searchParams.set('capability_code', input.capabilityCode);
  url.searchParams.set('source_ref', input.sourceRef.trim());
  if (input.artifactId?.trim()) {
    url.searchParams.set('artifact_id', input.artifactId.trim());
  }
  const response = await (input.fetchImpl || fetch)(apiBase ? url.toString() : `${url.pathname}${url.search}`, {
    credentials: 'same-origin',
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = isRecord(payload) && typeof payload.detail === 'string'
      ? payload.detail.trim()
      : '';
    throw new MotionPracticeReferenceProfileClientError(
      detail || `motion_reference_profile_request_failed_${response.status}`,
      response.status,
    );
  }
  return parseMotionPracticeReferenceProfileSelection(payload);
}
