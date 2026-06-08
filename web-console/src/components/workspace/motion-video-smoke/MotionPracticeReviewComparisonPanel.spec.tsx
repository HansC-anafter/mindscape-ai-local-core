import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MotionPracticeReviewComparisonPanel } from './MotionPracticeReviewComparisonPanel';
import { extractPracticeReviewResult } from './practiceReviewResultClient';

const reviewPayload = {
  status: 'completed',
  outputs: {
    practice_session_id: 'practice_1',
    practice_review_projection: {
      projection_status: 'complete',
      course_chapters: [
        {
          chapter_id: 'chapter_1',
          title: 'Warmup',
          start_ms: 0,
          end_ms: 5000,
          guidance_points: ['Set the breath cadence.'],
        },
      ],
      learner_practice_segments: [
        {
          segment_id: 'segment_1',
          chapter_id: 'chapter_1',
          start_ms: 1000,
          end_ms: 4000,
          motion_window_refs: ['window_1'],
          top_findings: ['Breath cadence is steady.'],
          confidence: 0.82,
          window_count: 1,
        },
      ],
      chapter_feedback: [
        {
          chapter_id: 'chapter_1',
          learner_segment_id: 'segment_1',
          meeting_feedback: ['Breath cadence is steady.'],
          summary_confidence: 'complete',
          evidence_refs: ['window_1'],
        },
      ],
    },
  },
};

function mockFetch(payload: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => payload,
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('MotionPracticeReviewComparisonPanel', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('extracts practice review projection from a playbook result payload', () => {
    const result = extractPracticeReviewResult(reviewPayload);

    expect(result.status).toBe('completed');
    expect(result.projection?.projection_status).toBe('complete');
    expect(result.projection?.course_chapters?.[0]?.title).toBe('Warmup');
  });

  it('renders course chapters and learner practice from one result request', async () => {
    const fetchMock = mockFetch(reviewPayload);

    render(
      <MotionPracticeReviewComparisonPanel
        apiUrl="http://api.test"
        executionId="exec_1"
      />,
    );

    expect(await screen.findByText('Warmup')).toBeTruthy();
    expect(screen.getByText('Set the breath cadence.')).toBeTruthy();
    expect(screen.getAllByText('Breath cadence is steady.').length).toBeGreaterThan(0);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(
      'http://api.test/api/v1/playbooks/execute/exec_1/result',
    );
  });

  it('shows missing chapter status without fabricating learner columns', async () => {
    mockFetch({
      status: 'completed',
      outputs: {
        practice_review_projection: {
          projection_status: 'missing_course_chapters',
          course_chapters: [],
          learner_practice_segments: [],
          chapter_feedback: [],
        },
      },
    });

    render(
      <MotionPracticeReviewComparisonPanel
        apiUrl="http://api.test"
        executionId="exec_missing"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('motion-practice-review-missing-chapters')).toBeTruthy();
    });
    expect(screen.queryByTestId('motion-practice-review-chapters')).toBeNull();
  });
});
