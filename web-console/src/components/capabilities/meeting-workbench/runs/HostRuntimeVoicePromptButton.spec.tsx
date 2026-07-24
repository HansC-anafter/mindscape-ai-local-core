import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { HostRuntimeVoicePromptButton } from './HostRuntimeVoicePromptButton';

const mocks = vi.hoisted(() => ({
  blobToBase64Audio: vi.fn(async () => 'UklGRg=='),
  submitVoiceTurn: vi.fn(),
  dispatchMeetingClientAction: vi.fn(),
  transcribeHostRuntimeAudio: vi.fn(),
  stopTrack: vi.fn(),
}));

vi.mock('@/lib/meeting-voice/voiceTurnClient', () => ({
  blobToBase64Audio: mocks.blobToBase64Audio,
  submitVoiceTurn: mocks.submitVoiceTurn,
}));

vi.mock('@/lib/meeting-voice/meetingClientActionEvent', () => ({
  dispatchMeetingClientAction: mocks.dispatchMeetingClientAction,
}));

vi.mock('./hostRuntimeSpeechToTextClient', () => ({
  transcribeHostRuntimeAudio: mocks.transcribeHostRuntimeAudio,
}));

class TestMediaRecorder {
  static isTypeSupported = vi.fn(() => true);

  mimeType: string;
  state: RecordingState = 'inactive';
  ondataavailable: ((event: BlobEvent) => void) | null = null;
  onstop: (() => void) | null = null;

  constructor(_stream: MediaStream, options?: MediaRecorderOptions) {
    this.mimeType = options?.mimeType || 'audio/webm';
  }

  start() {
    this.state = 'recording';
  }

  stop() {
    this.state = 'inactive';
    this.ondataavailable?.({
      data: new Blob(['voice'], { type: this.mimeType }),
    } as BlobEvent);
    this.onstop?.();
  }
}

async function recordOneTurn() {
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'Start voice prompt' }));
  });
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'Stop voice prompt' }));
    await Promise.resolve();
  });
}

describe('HostRuntimeVoicePromptButton', () => {
  beforeEach(() => {
    vi.stubGlobal('MediaRecorder', TestMediaRecorder);
    vi.stubGlobal('navigator', {
      mediaDevices: {
        getUserMedia: vi.fn(async () => ({
          getTracks: () => [{ stop: mocks.stopTrack }],
        })),
      },
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it('routes active meeting voice through Meeting Engine and dispatches a pack client action', async () => {
    const commandResponse = { command_id: 'cmd_prepare' };
    mocks.submitVoiceTurn.mockResolvedValue({
      status: 'transcribed_command_submitted',
      transcript: '播放瑜伽練習',
      command_response: commandResponse,
    });
    mocks.dispatchMeetingClientAction.mockReturnValue({ actionId: 'cmd_prepare' });
    const onTranscript = vi.fn();

    render(
      <HostRuntimeVoicePromptButton
        apiUrl="http://api.test"
        workspaceId="ws_test"
        meetingId="mtg_test"
        onTranscript={onTranscript}
      />,
    );

    await recordOneTurn();

    expect(mocks.submitVoiceTurn).toHaveBeenCalledWith(expect.objectContaining({
      apiBase: 'http://api.test',
      workspaceId: 'ws_test',
      meetingId: 'mtg_test',
      audioBase64: 'UklGRg==',
    }));
    expect(mocks.dispatchMeetingClientAction).toHaveBeenCalledWith(commandResponse);
    expect(onTranscript).not.toHaveBeenCalled();
    expect(mocks.transcribeHostRuntimeAudio).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Start voice prompt' })).toHaveAttribute(
      'title',
      'Transcript: 播放瑜伽練習',
    );
  });

  it('keeps ordinary Meeting Engine transcripts in the host runtime composer', async () => {
    mocks.submitVoiceTurn.mockResolvedValue({
      status: 'transcribed_command_submitted',
      transcript: '檢查目前狀態',
      command_response: { command_id: 'cmd_generic' },
    });
    mocks.dispatchMeetingClientAction.mockReturnValue(null);
    const onTranscript = vi.fn();

    render(
      <HostRuntimeVoicePromptButton
        apiUrl="http://api.test"
        workspaceId="ws_test"
        meetingId="mtg_test"
        onTranscript={onTranscript}
      />,
    );

    await recordOneTurn();

    expect(onTranscript).toHaveBeenCalledWith('檢查目前狀態');
  });
});
