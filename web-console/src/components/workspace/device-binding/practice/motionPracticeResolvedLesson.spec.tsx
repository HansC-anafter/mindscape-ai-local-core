// @vitest-environment jsdom

import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  buildResolvedMotionPracticeLessonHandoff,
  clearMotionPracticeReferenceProfileResolutionCacheForTests,
  useMotionPracticeResolvedLesson,
} from './motionPracticeResolvedLesson';

const handoff = {
  capabilityCode: 'yogacoach' as const,
  sourceKind: 'bilibili_instruction_ref' as const,
  sourceValue: 'https://www.bilibili.com/video/BV13g4y1u7di/?tracking=1',
  sourceProvider: 'bilibili',
  sourceTitle: 'Bilibili yoga practice reference',
};

const selection = {
  status: 'ready' as const,
  artifact_id: 'artifact-terminal',
  reference_profile_id: 'profile-v3',
  source_ref: 'https://www.bilibili.com/video/BV13g4y1u7di/',
  chapter_count: 1,
  duration_ms: 42000,
  chapters: [
    {
      chapter_id: 'chapter-1',
      title: 'Standing flow',
      start_ms: 0,
      end_ms: 42000,
      segment_type: 'flow',
      confidence: 0.94,
    },
  ],
};

afterEach(() => {
  clearMotionPracticeReferenceProfileResolutionCacheForTests();
  vi.unstubAllGlobals();
});

describe('useMotionPracticeResolvedLesson', () => {
  it('enriches the handoff with canonical chapters and artifact identity', () => {
    const resolved = buildResolvedMotionPracticeLessonHandoff(handoff, selection);

    expect(resolved).toMatchObject({
      sourceValue: selection.source_ref,
      motionReferenceProfileArtifactId: 'artifact-terminal',
      referenceProfileResolutionStatus: 'ready',
    });
    expect(JSON.parse(resolved.courseChaptersInput || '')).toEqual(selection.chapters);
  });

  it('singleflights duplicate consumers for the same reference identity', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(selection), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);
    const input = {
      apiUrl: 'http://api.test',
      workspaceId: 'workspace-one',
      handoff,
    };

    const first = renderHook(() => useMotionPracticeResolvedLesson(input));
    const second = renderHook(() => useMotionPracticeResolvedLesson(input));

    expect(first.result.current.status).toBe('resolving');
    await waitFor(() => {
      expect(first.result.current.status).toBe('ready');
      expect(second.result.current.status).toBe('ready');
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('projects conflict as a terminal failed handoff', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      detail: 'motion_reference_profile_source_conflict',
    }), {
      status: 409,
      headers: { 'Content-Type': 'application/json' },
    })));

    const rendered = renderHook(() => useMotionPracticeResolvedLesson({
      apiUrl: 'http://api.test',
      workspaceId: 'workspace-one',
      handoff,
    }));

    await waitFor(() => expect(rendered.result.current.status).toBe('failed'));
    expect(rendered.result.current.handoff).toMatchObject({
      referenceProfileResolutionStatus: 'failed',
      referenceProfileResolutionError: 'The selected reference has conflicting terminal motion profiles.',
    });
  });
});
