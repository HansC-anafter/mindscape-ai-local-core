import { describe, expect, it } from 'vitest';

import {
  parseMotionPracticeCourseChaptersInput,
  resolveMotionPracticeExpectedDurationMs,
} from './motionPracticeInstructionSource';

describe('motion practice instruction duration', () => {
  it('uses the final semantic chapter end as the playback and receiver duration', () => {
    const parsed = parseMotionPracticeCourseChaptersInput(JSON.stringify([
      {
        chapter_id: 'chapter-1',
        title: 'Warm up',
        start_ms: 0,
        end_ms: 12000,
      },
      {
        chapter_id: 'chapter-2',
        title: 'Standing flow',
        start_ms: 12000,
        end_ms: 1809679,
      },
    ]));

    expect(parsed.error).toBeNull();
    expect(resolveMotionPracticeExpectedDurationMs({
      kind: 'bilibili_instruction_ref',
      value: 'https://www.bilibili.com/video/BV13g4y1u7di/',
      courseChapters: parsed.courseChapters,
    })).toBe(1809679);
  });
});
