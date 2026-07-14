import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  buildMotionPracticeInstructionRefs,
  MotionPracticeInstructionSourcePanel,
  parseMotionPracticeCourseChaptersInput,
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
      kind: 'bilibili_instruction_ref',
      value: 'https://www.bilibili.com/video/BV13g4y1u7di/',
    })).toEqual([
      {
        ref_type: 'video_instruction_ref',
        source_provider: 'bilibili',
        video_ref: 'https://www.bilibili.com/video/BV13g4y1u7di/',
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
            segment_type: 'unknown',
            scoreable: true,
            match_role: 'instruction',
            guidance_mode: 'score',
          },
        ],
        segment_graph: {
          graph_version: 'motion_reference_segment_graph.v1',
          ordered_edges: [],
          scoreable_segment_ids: ['chapter_1'],
          unordered_match_enabled: true,
          resync_policy: {
            ordered_prior_enabled: true,
            unordered_fallback_enabled: true,
            skip_non_scoreable_segments: true,
          },
        },
      },
    ]);
  });

  it('parses materialized course chapters from shared video understanding output', () => {
    expect(parseMotionPracticeCourseChaptersInput(JSON.stringify([
      {
        id: 'vcs_chapter_1',
        display_label: 'Standing alignment',
        start_time: 1.2,
        end_time: 6.4,
        guidance_points: ['Lift through the spine'],
      },
    ]))).toEqual({
      courseChapters: [
        {
          id: 'vcs_chapter_1',
          display_label: 'Standing alignment',
          chapter_id: 'vcs_chapter_1',
          title: 'Standing alignment',
          start_time: 1.2,
          end_time: 6.4,
          start_ms: 1200,
          end_ms: 6400,
          segment_type: 'unknown',
          scoreable: true,
          match_role: 'instruction',
          guidance_mode: 'score',
          guidance_points: ['Lift through the spine'],
        },
      ],
      error: null,
    });
  });

  it('normalizes mixed long-form course segments into scoreable graph metadata', () => {
    const parsed = parseMotionPracticeCourseChaptersInput(JSON.stringify([
      {
        chapter_id: 'opening_chat',
        title: 'Opening chat',
        start_ms: 0,
        end_ms: 180000,
      },
      {
        chapter_id: 'sun_flow',
        title: 'Sun salutation flow',
        start_ms: 180000,
        end_ms: 480000,
      },
      {
        chapter_id: 'water_break',
        title: 'Rest break',
        start_ms: 480000,
        end_ms: 540000,
      },
      {
        chapter_id: 'warrior_demo',
        title: 'Warrior pose demo',
        start_ms: 540000,
        end_ms: 720000,
        segment_type: 'demo',
      },
    ]));

    expect(parsed.error).toBeNull();
    expect(parsed.courseChapters).toEqual([
      expect.objectContaining({
        chapter_id: 'opening_chat',
        segment_type: 'chat',
        scoreable: false,
        guidance_mode: 'suppress',
      }),
      expect.objectContaining({
        chapter_id: 'sun_flow',
        segment_type: 'practice',
        scoreable: true,
        guidance_mode: 'score',
      }),
      expect.objectContaining({
        chapter_id: 'water_break',
        segment_type: 'rest',
        scoreable: false,
        guidance_mode: 'suppress',
      }),
      expect.objectContaining({
        chapter_id: 'warrior_demo',
        segment_type: 'demo',
        scoreable: true,
        guidance_mode: 'score',
      }),
    ]);

    const refs = buildMotionPracticeInstructionRefs({
      kind: 'bilibili_instruction_ref',
      value: 'https://www.bilibili.com/video/BV13g4y1u7di/',
      courseChapters: parsed.courseChapters,
    });

    expect(refs[0].segment_graph).toEqual({
      graph_version: 'motion_reference_segment_graph.v1',
      ordered_edges: [
        { from: 'opening_chat', to: 'sun_flow', relation: 'next' },
        { from: 'sun_flow', to: 'water_break', relation: 'next' },
        { from: 'water_break', to: 'warrior_demo', relation: 'next' },
      ],
      scoreable_segment_ids: ['sun_flow', 'warrior_demo'],
      unordered_match_enabled: true,
      resync_policy: {
        ordered_prior_enabled: true,
        unordered_fallback_enabled: true,
        skip_non_scoreable_segments: true,
      },
    });
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
      courseChapters: undefined,
      courseChaptersInput: undefined,
      courseChaptersError: undefined,
    });
    expect(setIntervalSpy).not.toHaveBeenCalled();
    setIntervalSpy.mockRestore();
  });

  it('updates controlled materialized chapters without fetching or polling', () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');
    const onChange = vi.fn();
    const source: MotionPracticeInstructionSourceState = {
      kind: 'manual_teacher_ref',
      value: 'mindscape://teacher/ref',
    };
    const chaptersInput = JSON.stringify([
      {
        chapter_id: 'chapter_1',
        title: 'Warmup',
        start_ms: 0,
        end_ms: 5000,
      },
    ]);

    render(
      <MotionPracticeInstructionSourcePanel
        source={source}
        onChange={onChange}
      />,
    );

    fireEvent.change(screen.getByTestId('motion-practice-course-chapters-input'), {
      target: { value: chaptersInput },
    });

    expect(onChange).toHaveBeenCalledWith({
      kind: 'manual_teacher_ref',
      value: 'mindscape://teacher/ref',
      courseChaptersInput: chaptersInput,
      courseChapters: [
        {
          chapter_id: 'chapter_1',
          title: 'Warmup',
          start_ms: 0,
          end_ms: 5000,
          segment_type: 'unknown',
          scoreable: true,
          match_role: 'instruction',
          guidance_mode: 'score',
        },
      ],
      courseChaptersError: null,
    });
    expect(setIntervalSpy).not.toHaveBeenCalled();
    setIntervalSpy.mockRestore();
  });

  it('blocks invalid materialized chapter input from becoming launchable chapters', () => {
    const onChange = vi.fn();
    const source: MotionPracticeInstructionSourceState = {
      kind: 'manual_teacher_ref',
      value: 'mindscape://teacher/ref',
    };

    render(
      <MotionPracticeInstructionSourcePanel
        source={source}
        onChange={onChange}
      />,
    );

    fireEvent.change(screen.getByTestId('motion-practice-course-chapters-input'), {
      target: { value: '{"chapter_id":"bad"}' },
    });

    expect(onChange).toHaveBeenCalledWith({
      kind: 'manual_teacher_ref',
      value: 'mindscape://teacher/ref',
      courseChaptersInput: '{"chapter_id":"bad"}',
      courseChapters: [],
      courseChaptersError: 'Course chapters must be a JSON array.',
    });
  });
});
