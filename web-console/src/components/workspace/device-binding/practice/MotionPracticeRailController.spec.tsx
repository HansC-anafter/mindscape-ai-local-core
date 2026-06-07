import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi, afterEach } from 'vitest';

import { MotionPracticeRailController } from './MotionPracticeRailController';
import { launchMotionPractice } from '../motionPracticeLauncher';
import type { DeviceSessionEntry } from '@/lib/device-binding/deviceBindingClient';

const mocks = vi.hoisted(() => ({
  launchMotionPractice: vi.fn(async () => ({
    meetingId: 'mtg_motion',
    commandId: 'cmd_motion',
    liveSessionId: 'lms_motion',
    sourceSessionId: 'session_1',
    status: 'accepted',
  })),
}));

vi.mock('../motionPracticeLauncher', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../motionPracticeLauncher')>();
  return {
    ...actual,
    launchMotionPractice: mocks.launchMotionPractice,
  };
});

const sourceSession: DeviceSessionEntry = {
  session_id: 'session_1',
  workspace_id: 'ws_device',
  pairing_code: 'PAIR1234',
  device_id: 'phone_1',
  display_name: 'Phone',
  source_types: ['phone_camera'],
  state: 'active',
  created_at_epoch: 1,
  updated_at_epoch: 1,
  expires_at_epoch: 61,
};

describe('MotionPracticeRailController', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('launches practice with selected instruction refs and no interval polling', async () => {
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');
    const onResultChange = vi.fn();

    render(
      <MotionPracticeRailController
        apiUrl="http://api.test"
        workspaceId="ws_device"
        sessions={[sourceSession]}
        result={null}
        onResultChange={onResultChange}
      />,
    );

    fireEvent.change(screen.getByTestId('motion-practice-instruction-source-kind'), {
      target: { value: 'youtube_instruction_ref' },
    });
    fireEvent.change(screen.getByTestId('motion-practice-instruction-source-value'), {
      target: { value: 'https://www.youtube.com/watch?v=demo' },
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId('motion-practice-start-button'));
    });

    expect(launchMotionPractice).toHaveBeenCalledTimes(1);
    expect(launchMotionPractice).toHaveBeenCalledWith(
      expect.objectContaining({
        workspaceId: 'ws_device',
        sourceSession,
        coachPack: 'yogacoach',
        practiceMode: 'record_summary',
        instructionRefs: [
          {
            ref_type: 'youtube_instruction_ref',
            source_provider: 'youtube',
            video_ref: 'https://www.youtube.com/watch?v=demo',
            frame_readable: false,
            motion_analysis_source: false,
          },
        ],
      }),
    );
    expect(onResultChange).toHaveBeenNthCalledWith(1, null);
    expect(onResultChange).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ commandId: 'cmd_motion' }),
    );
    expect(setIntervalSpy).not.toHaveBeenCalled();
    setIntervalSpy.mockRestore();
  });

  it('blocks non-ready live guidance routes without submitting', () => {
    render(
      <MotionPracticeRailController
        apiUrl="http://api.test"
        workspaceId="ws_device"
        sessions={[sourceSession]}
        result={null}
        onResultChange={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Dance' }));
    fireEvent.change(screen.getByTestId('motion-practice-mode-select'), {
      target: { value: 'live_guidance' },
    });

    expect(screen.getByTestId('motion-practice-readiness')).toHaveTextContent(
      'Dance live guidance and teacher assessment are pending.',
    );
    expect(screen.getByTestId('motion-practice-start-button')).toBeDisabled();
    expect(launchMotionPractice).not.toHaveBeenCalled();
  });
});
