import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  buildMotionPracticeInstructionRefs,
  MotionPracticeInstructionSourcePanel,
  type MotionPracticeInstructionSourceState,
} from './MotionPracticeInstructionSourcePanel';

describe('MotionPracticeInstructionSourcePanel', () => {
  it('serializes local video, YouTube, and manual teacher refs without raw media', () => {
    expect(buildMotionPracticeInstructionRefs({
      kind: 'local_video_smoke_ref',
      value: '',
    })).toEqual([
      {
        ref_type: 'local_video_smoke_ref',
        source_provider: 'local_video',
        media_ref: 'mindscape://motion-video-smoke/current',
        frame_readable: false,
        motion_analysis_source: true,
      },
    ]);

    expect(buildMotionPracticeInstructionRefs({
      kind: 'youtube_instruction_ref',
      value: 'https://www.youtube.com/watch?v=demo',
    })).toEqual([
      {
        ref_type: 'youtube_instruction_ref',
        source_provider: 'youtube',
        video_ref: 'https://www.youtube.com/watch?v=demo',
        frame_readable: false,
        motion_analysis_source: false,
      },
    ]);

    expect(buildMotionPracticeInstructionRefs({
      kind: 'manual_teacher_ref',
      value: 'mindscape://teacher/ref',
    })).toEqual([
      {
        ref_type: 'manual_teacher_ref',
        source_provider: 'manual',
        teacher_ref: 'mindscape://teacher/ref',
        frame_readable: false,
        motion_analysis_source: false,
      },
    ]);
  });

  it('attaches upstream course chapters to instruction refs', () => {
    expect(buildMotionPracticeInstructionRefs({
      kind: 'local_video_smoke_ref',
      value: 'mindscape://motion-video-smoke/session/demo',
      courseChapters: [
        {
          chapter_id: 'chapter_1',
          title: 'Warmup',
          start_ms: 0,
          end_ms: 5000,
        },
      ],
    })).toEqual([
      {
        ref_type: 'local_video_smoke_ref',
        source_provider: 'local_video',
        media_ref: 'mindscape://motion-video-smoke/session/demo',
        frame_readable: false,
        motion_analysis_source: true,
        course_chapters: [
          {
            chapter_id: 'chapter_1',
            title: 'Warmup',
            start_ms: 0,
            end_ms: 5000,
          },
        ],
      },
    ]);
  });

  it('updates controlled source state without creating an interval loop', () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');
    const onChange = vi.fn();
    const source: MotionPracticeInstructionSourceState = {
      kind: 'manual_teacher_ref',
      value: '',
    };

    render(
      <MotionPracticeInstructionSourcePanel
        source={source}
        onChange={onChange}
      />,
    );

    fireEvent.change(screen.getByTestId('motion-practice-instruction-source-kind'), {
      target: { value: 'youtube_instruction_ref' },
    });

    expect(onChange).toHaveBeenCalledWith({
      kind: 'youtube_instruction_ref',
      value: '',
    });
    expect(setIntervalSpy).not.toHaveBeenCalled();
    setIntervalSpy.mockRestore();
  });
});
