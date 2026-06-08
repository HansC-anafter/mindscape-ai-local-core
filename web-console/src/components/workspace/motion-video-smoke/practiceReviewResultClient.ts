'use client';

export type PracticeReviewCourseChapter = {
  chapter_id: string;
  chapter_index?: number;
  title: string;
  start_ms: number;
  end_ms: number;
  guidance_points?: string[];
  source_ref?: string | null;
};

export type PracticeReviewLearnerSegment = {
  segment_id: string;
  chapter_id: string;
  start_ms: number;
  end_ms: number;
  motion_window_refs?: string[];
  top_findings?: string[];
  confidence?: number;
  window_count?: number;
  truncated?: boolean;
};

export type PracticeReviewChapterFeedback = {
  chapter_id: string;
  learner_segment_id?: string | null;
  meeting_feedback?: string[];
  summary_confidence?: string;
  evidence_refs?: string[];
};

export type PracticeReviewProjection = {
  schema_version?: string;
  projection_status: 'complete' | 'partial' | 'missing_course_chapters';
  course_chapters?: PracticeReviewCourseChapter[];
  learner_practice_segments?: PracticeReviewLearnerSegment[];
  chapter_feedback?: PracticeReviewChapterFeedback[];
  resource_policy?: Record<string, unknown>;
  truncated?: boolean;
};

export type PracticeReviewResult = {
  status: string;
  summary: Record<string, unknown> | null;
  projection: PracticeReviewProjection | null;
};

export type FetchPracticeReviewResultArgs = {
  apiUrl?: string;
  executionId: string;
  signal?: AbortSignal;
};

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

function resolveApiBase(apiUrl = ''): string {
  if (apiUrl.trim()) {
    return trimTrailingSlash(apiUrl.trim());
  }
  if (typeof window !== 'undefined') {
    return window.location.origin;
  }
  return '';
}

function buildApiUrl(apiUrl: string | undefined, path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const apiBase = resolveApiBase(apiUrl || '');
  return apiBase ? `${apiBase}${normalizedPath}` : normalizedPath;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function readProjection(value: unknown): PracticeReviewProjection | null {
  if (!isRecord(value)) {
    return null;
  }
  const status = readString(value.projection_status);
  if (!status) {
    return null;
  }
  return value as PracticeReviewProjection;
}

function readStudentSummary(payload: unknown): Record<string, unknown> | null {
  if (!isRecord(payload)) {
    return null;
  }
  const candidates: unknown[] = [
    payload,
    payload.outputs,
    payload.step_outputs,
  ];
  if (isRecord(payload.context)) {
    const yogaContext = payload.context.yogacoach_student_practice_summary;
    if (isRecord(yogaContext)) {
      candidates.push(yogaContext.build_student_practice_summary);
    }
  }
  if (isRecord(payload.steps)) {
    const yogaStep = payload.steps.yogacoach_student_practice_summary;
    if (isRecord(yogaStep)) {
      candidates.push(yogaStep.outputs);
      if (isRecord(yogaStep.step_outputs)) {
        candidates.push(yogaStep.step_outputs.build_student_practice_summary);
      }
    }
  }
  for (const candidate of candidates) {
    if (!isRecord(candidate)) {
      continue;
    }
    if (readProjection(candidate.practice_review_projection)) {
      return candidate;
    }
    const buildOutput = candidate.build_student_practice_summary;
    if (isRecord(buildOutput) && readProjection(buildOutput.practice_review_projection)) {
      return buildOutput;
    }
  }
  return null;
}

export function extractPracticeReviewResult(payload: unknown): PracticeReviewResult {
  const summary = readStudentSummary(payload);
  return {
    status: isRecord(payload) ? readString(payload.status) || 'unknown' : 'unknown',
    summary,
    projection: summary ? readProjection(summary.practice_review_projection) : null,
  };
}

export async function fetchPracticeReviewResult({
  apiUrl = '',
  executionId,
  signal,
}: FetchPracticeReviewResultArgs): Promise<PracticeReviewResult> {
  const normalizedExecutionId = executionId.trim();
  if (!normalizedExecutionId) {
    throw new Error('practice_review_execution_id_required');
  }
  const response = await fetch(
    buildApiUrl(
      apiUrl,
      `/api/v1/playbooks/execute/${encodeURIComponent(normalizedExecutionId)}/result`,
    ),
    {
      credentials: 'same-origin',
      signal,
    },
  );
  if (!response.ok) {
    throw new Error(`practice_review_result_request_failed:${response.status}`);
  }
  return extractPracticeReviewResult(await response.json());
}
