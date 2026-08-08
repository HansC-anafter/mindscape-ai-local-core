import { describe, expect, it, vi } from 'vitest';

import {
  fetchMotionPracticeReferenceProfileSelection,
  MotionPracticeReferenceProfileClientError,
  parseMotionPracticeReferenceProfileSelection,
} from './motionPracticeReferenceProfileClient';

const selection = {
  status: 'ready',
  artifact_id: 'artifact-terminal',
  reference_profile_id: 'profile-v3',
  source_ref: 'https://www.bilibili.com/video/BV13g4y1u7di/',
  chapter_count: 2,
  duration_ms: 42000,
  chapters: [
    {
      chapter_id: 'chapter-1',
      title: 'Warm up',
      start_ms: 0,
      end_ms: 12000,
      segment_type: 'transition',
      confidence: 0.91,
    },
    {
      chapter_id: 'chapter-2',
      title: 'Standing flow',
      start_ms: 12000,
      end_ms: 42000,
      segment_type: 'flow',
      confidence: 0.94,
    },
  ],
} as const;

describe('motionPracticeReferenceProfileClient', () => {
  it('loads one workspace-scoped bounded selection request', async () => {
    const calls: Array<[RequestInfo | URL, RequestInit | undefined]> = [];
    const fetchImpl: typeof fetch = async (request, init) => {
      calls.push([request, init]);
      return new Response(JSON.stringify(selection), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    };

    const result = await fetchMotionPracticeReferenceProfileSelection({
      apiUrl: 'https://remote-workbench.mindscapeai.app/',
      workspaceId: 'workspace-one',
      capabilityCode: 'yogacoach',
      sourceRef: 'https://www.bilibili.com/video/BV13g4y1u7di/?tracking=1',
      fetchImpl,
    });

    expect(result.chapter_count).toBe(2);
    expect(calls).toHaveLength(1);
    const [requestUrl, requestInit] = calls[0];
    const url = new URL(String(requestUrl));
    expect(url.pathname).toBe(
      '/api/v1/workspaces/workspace-one/motion-reference-profiles/selection',
    );
    expect(url.searchParams.get('source_ref')).toBe(
      'https://www.bilibili.com/video/BV13g4y1u7di/?tracking=1',
    );
    expect(url.searchParams.getAll('capability_code')).toEqual(['yogacoach']);
    expect(requestInit).toMatchObject({ credentials: 'same-origin' });
  });

  it('rejects an unbounded or mismatched chapter payload', () => {
    expect(() => parseMotionPracticeReferenceProfileSelection({
      ...selection,
      chapter_count: 3,
    })).toThrowError(
      new MotionPracticeReferenceProfileClientError(
        'motion_reference_profile_chapter_count_mismatch',
        502,
      ),
    );
  });

  it('preserves the backend fail-closed reason', async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({
      detail: 'motion_reference_profile_source_conflict',
    }), {
      status: 409,
      headers: { 'Content-Type': 'application/json' },
    }));

    await expect(fetchMotionPracticeReferenceProfileSelection({
      apiUrl: 'http://api.test',
      workspaceId: 'workspace-one',
      capabilityCode: 'dance_motion_coach',
      sourceRef: selection.source_ref,
      fetchImpl: fetchImpl as typeof fetch,
    })).rejects.toMatchObject({
      code: 'motion_reference_profile_source_conflict',
      status: 409,
    });
  });
});
