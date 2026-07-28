import { describe, expect, it } from 'vitest';

import type { AOLMeetingClientAction } from '@/lib/meeting-voice/meetingClientActionEvent';
import {
  buildReferencePlaybackEmbedUrl,
  buildStartedMotionPracticeReferencePlayback,
  confirmMotionPracticeReferencePlayback,
  prepareMotionPracticeReferencePlayback,
} from './motionPracticeReferencePlayback';

const prepareAction: AOLMeetingClientAction = {
  schemaVersion: 'aol.client_action.v1',
  actionId: 'cmd_prepare',
  workspaceId: 'ws_test',
  meetingId: 'mtg_test',
  packCode: 'yogacoach',
  intentCode: 'prepare_default_reference_practice',
  actionCode: 'yogacoach.prepare_reference_practice',
  requiresConfirmation: true,
  payload: {
    reference: {
      owner_pack: 'social_video_refs',
      object_kind: 'instruction_ref',
      provider: 'bilibili',
      provider_video_id: 'BV13g4y1u7di',
      source_kind: 'bilibili_instruction_ref',
      source_url: 'https://www.bilibili.com/video/BV13g4y1u7di/',
      title: 'Bilibili 30-minute yoga practice',
    },
    playback: { start_ms: 0, duration_ms: 1_800_000, loop: false },
  },
};

describe('motionPracticeReferencePlayback', () => {
  it('builds one pending handoff without treating 30 minutes as chapter segmentation', () => {
    const prepared = prepareMotionPracticeReferencePlayback(prepareAction);
    expect(prepared?.handoff.sourceValue).toBe(
      'https://www.bilibili.com/video/BV13g4y1u7di/',
    );
    expect(prepared?.plan.status).toBe('awaiting_confirmation');
    expect(prepared?.plan.playback.durationMs).toBe(1_800_000);
    expect((prepared?.handoff as any).courseChaptersInput).toBeUndefined();
  });

  it('accepts confirmation only for the same pending workspace and meeting', () => {
    const prepared = prepareMotionPracticeReferencePlayback(prepareAction)!;
    const confirmed = confirmMotionPracticeReferencePlayback(prepared.plan, {
      ...prepareAction,
      actionId: 'cmd_confirm',
      intentCode: 'confirm_reference_practice',
      actionCode: 'yogacoach.confirm_reference_practice',
      requiresConfirmation: false,
      payload: { countdown_seconds: 5 },
    });
    expect(confirmed).toMatchObject({
      status: 'countdown',
      countdownRemaining: 5,
      confirmationActionId: 'cmd_confirm',
    });
    expect(confirmMotionPracticeReferencePlayback(prepared.plan, {
      ...prepareAction,
      actionId: 'cmd_wrong',
      meetingId: 'mtg_other',
      actionCode: 'yogacoach.confirm_reference_practice',
      payload: { countdown_seconds: 5 },
    })).toBeNull();
  });

  it('builds an autoplay Bilibili embed for the reference lane', () => {
    const plan = prepareMotionPracticeReferencePlayback(prepareAction)!.plan;
    const url = new URL(buildReferencePlaybackEmbedUrl(plan));
    expect(url.hostname).toBe('player.bilibili.com');
    expect(url.searchParams.get('bvid')).toBe('BV13g4y1u7di');
    expect(url.searchParams.get('autoplay')).toBe('1');
  });

  it('projects a successful direct launch into the existing playback plan', () => {
    const started = buildStartedMotionPracticeReferencePlayback({
      workspaceId: 'ws_test',
      meetingId: 'mtg_direct',
      handoff: {
        capabilityCode: 'yogacoach',
        sourceKind: 'bilibili_instruction_ref',
        sourceValue: 'https://www.bilibili.com/video/BV13g4y1u7di/',
        sourceProvider: 'bilibili',
        sourceTitle: 'Bilibili yoga practice reference',
      },
      durationMs: 1_809_679,
      startedAt: '2026-07-28T16:00:00.000Z',
    });

    expect(started).toMatchObject({
      workspaceId: 'ws_test',
      meetingId: 'mtg_direct',
      status: 'playing',
      reference: {
        provider: 'bilibili',
        providerVideoId: 'BV13g4y1u7di',
      },
      playback: {
        startMs: 0,
        durationMs: 1_809_679,
        loop: false,
      },
      startedAt: '2026-07-28T16:00:00.000Z',
    });
  });
});
