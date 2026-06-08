'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';

import {
  fetchPracticeReviewResult,
  type PracticeReviewChapterFeedback,
  type PracticeReviewCourseChapter,
  type PracticeReviewLearnerSegment,
  type PracticeReviewProjection,
  type PracticeReviewResult,
} from './practiceReviewResultClient';

interface MotionPracticeReviewComparisonPanelProps {
  apiUrl?: string;
  executionId: string;
}

function formatTimeRange(startMs: number, endMs: number): string {
  const start = Math.max(0, Math.round(startMs / 1000));
  const end = Math.max(start, Math.round(endMs / 1000));
  return `${start}s - ${end}s`;
}

function readArray<T>(value: T[] | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

function groupSegmentsByChapter(
  projection: PracticeReviewProjection | null,
): Map<string, PracticeReviewLearnerSegment[]> {
  const groups = new Map<string, PracticeReviewLearnerSegment[]>();
  for (const segment of readArray(projection?.learner_practice_segments)) {
    const chapterSegments = groups.get(segment.chapter_id) || [];
    chapterSegments.push(segment);
    groups.set(segment.chapter_id, chapterSegments);
  }
  return groups;
}

function groupFeedbackByChapter(
  projection: PracticeReviewProjection | null,
): Map<string, PracticeReviewChapterFeedback[]> {
  const groups = new Map<string, PracticeReviewChapterFeedback[]>();
  for (const feedback of readArray(projection?.chapter_feedback)) {
    const chapterFeedback = groups.get(feedback.chapter_id) || [];
    chapterFeedback.push(feedback);
    groups.set(feedback.chapter_id, chapterFeedback);
  }
  return groups;
}

function firstChapterId(chapters: PracticeReviewCourseChapter[]): string {
  return chapters[0]?.chapter_id || '';
}

export function MotionPracticeReviewComparisonPanel({
  apiUrl = '',
  executionId,
}: MotionPracticeReviewComparisonPanelProps) {
  const [result, setResult] = useState<PracticeReviewResult | null>(null);
  const [selectedChapterId, setSelectedChapterId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const normalizedExecutionId = executionId.trim();

  const loadResult = useCallback(async () => {
    if (!normalizedExecutionId) {
      setResult(null);
      setSelectedChapterId('');
      setError(null);
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      const nextResult = await fetchPracticeReviewResult({
        apiUrl,
        executionId: normalizedExecutionId,
        signal: controller.signal,
      });
      setResult(nextResult);
      const chapters = readArray(nextResult.projection?.course_chapters);
      setSelectedChapterId((current) => current || firstChapterId(chapters));
    } catch (nextError) {
      if (controller.signal.aborted) {
        return;
      }
      setError(nextError instanceof Error ? nextError.message : 'practice_review_result_failed');
      setResult(null);
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, [apiUrl, normalizedExecutionId]);

  useEffect(() => {
    void loadResult();
    return () => {
      abortRef.current?.abort();
    };
  }, [loadResult]);

  const projection = result?.projection || null;
  const chapters = readArray(projection?.course_chapters);
  const segmentsByChapter = useMemo(() => groupSegmentsByChapter(projection), [projection]);
  const feedbackByChapter = useMemo(() => groupFeedbackByChapter(projection), [projection]);
  const selectedChapter = chapters.find((chapter) => chapter.chapter_id === selectedChapterId)
    || chapters[0]
    || null;
  const selectedSegments = selectedChapter
    ? segmentsByChapter.get(selectedChapter.chapter_id) || []
    : [];
  const selectedFeedback = selectedChapter
    ? feedbackByChapter.get(selectedChapter.chapter_id) || []
    : [];

  return (
    <section
      className="rounded-md border border-neutral-800 bg-neutral-900 p-4"
      data-testid="motion-practice-review-comparison"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-neutral-800 pb-3">
        <div>
          <h2 className="text-lg font-semibold tracking-normal text-neutral-100">Practice review</h2>
          <p className="mt-1 text-xs text-neutral-400">
            {normalizedExecutionId || 'No execution selected'}
          </p>
        </div>
        <button
          type="button"
          className="inline-flex items-center justify-center gap-2 rounded border border-neutral-700 px-3 py-2 text-sm font-medium text-neutral-200 disabled:cursor-not-allowed disabled:text-neutral-500"
          disabled={!normalizedExecutionId || loading}
          onClick={() => void loadResult()}
          data-testid="motion-practice-review-refresh"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Refresh
        </button>
      </div>

      {!normalizedExecutionId && (
        <div className="py-8 text-center text-sm text-neutral-500">
          Select a completed execution.
        </div>
      )}

      {normalizedExecutionId && loading && (
        <div className="py-8 text-center text-sm text-neutral-400">Loading review...</div>
      )}

      {error && (
        <div className="mt-4 rounded border border-red-700 bg-red-950/40 p-3 text-sm text-red-100">
          {error}
        </div>
      )}

      {projection?.projection_status === 'missing_course_chapters' && (
        <div
          className="mt-4 rounded border border-amber-700 bg-amber-950/30 p-3 text-sm text-amber-100"
          data-testid="motion-practice-review-missing-chapters"
        >
          Course chapters are missing from this result.
        </div>
      )}

      {chapters.length > 0 && (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div className="min-w-0 rounded border border-neutral-800 bg-neutral-950 p-3">
            <h3 className="text-sm font-semibold text-neutral-200">Course chapters</h3>
            <div className="mt-3 space-y-2" data-testid="motion-practice-review-chapters">
              {chapters.map((chapter) => {
                const selected = selectedChapter?.chapter_id === chapter.chapter_id;
                return (
                  <button
                    type="button"
                    key={chapter.chapter_id}
                    className={`w-full rounded border px-3 py-2 text-left text-sm ${
                      selected
                        ? 'border-emerald-500 bg-emerald-950/30 text-emerald-100'
                        : 'border-neutral-800 bg-neutral-900 text-neutral-200 hover:border-neutral-600'
                    }`}
                    onClick={() => setSelectedChapterId(chapter.chapter_id)}
                  >
                    <span className="block font-medium">{chapter.title}</span>
                    <span className="mt-1 block text-xs text-neutral-400">
                      {formatTimeRange(chapter.start_ms, chapter.end_ms)}
                    </span>
                    {readArray(chapter.guidance_points).length > 0 && (
                      <span className="mt-2 block text-xs text-neutral-300">
                        {chapter.guidance_points?.[0]}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="min-w-0 rounded border border-neutral-800 bg-neutral-950 p-3">
            <h3 className="text-sm font-semibold text-neutral-200">Learner practice</h3>
            {selectedChapter && (
              <div className="mt-1 text-xs text-neutral-500">
                {selectedChapter.title} · {formatTimeRange(selectedChapter.start_ms, selectedChapter.end_ms)}
              </div>
            )}
            <div className="mt-3 space-y-3" data-testid="motion-practice-review-learner">
              {selectedSegments.length === 0 && (
                <div className="rounded border border-neutral-800 p-3 text-sm text-neutral-500">
                  No learner segment matched this chapter.
                </div>
              )}
              {selectedSegments.map((segment) => (
                <div key={segment.segment_id} className="rounded border border-neutral-800 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-neutral-200">
                    <span>{formatTimeRange(segment.start_ms, segment.end_ms)}</span>
                    <span className="text-xs text-neutral-400">
                      {segment.window_count || 0} windows · {Math.round((segment.confidence || 0) * 100)}%
                    </span>
                  </div>
                  {readArray(segment.top_findings).length > 0 && (
                    <ul className="mt-2 space-y-1 text-xs text-neutral-300">
                      {segment.top_findings?.map((finding) => (
                        <li key={finding}>{finding}</li>
                      ))}
                    </ul>
                  )}
                  {readArray(segment.motion_window_refs).length > 0 && (
                    <div className="mt-2 truncate text-[11px] text-neutral-500">
                      {segment.motion_window_refs?.[0]}
                    </div>
                  )}
                </div>
              ))}

              {selectedFeedback.map((feedback) => (
                <div
                  key={`${feedback.chapter_id}:${feedback.learner_segment_id || 'feedback'}`}
                  className="rounded border border-sky-800 bg-sky-950/20 p-3 text-sm text-sky-100"
                >
                  <div className="text-xs uppercase tracking-normal text-sky-300">
                    Meeting feedback
                  </div>
                  <ul className="mt-2 space-y-1">
                    {readArray(feedback.meeting_feedback).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export default MotionPracticeReviewComparisonPanel;
