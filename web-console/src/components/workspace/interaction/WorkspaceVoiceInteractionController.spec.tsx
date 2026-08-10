import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  WorkspaceInteractionIngressProvider,
  useWorkspaceInteractionTargetRegistration,
} from '@/lib/workspace-interaction/WorkspaceInteractionIngressProvider';
import type { WorkspaceInteractionTarget } from '@/lib/workspace-interaction/workspaceInteractionTarget';

const boundedMocks = vi.hoisted(() => ({
  supported: vi.fn(() => true),
  encode: vi.fn(async () => 'encoded-audio'),
  start: vi.fn(),
  input: null as null | {
    onComplete: (recording: unknown) => Promise<void>;
    onError: (error: Error) => void;
  },
}));

vi.mock('./workspaceBoundedVoiceTransport', () => ({
  isWorkspaceBoundedVoiceCaptureSupported: boundedMocks.supported,
  encodeWorkspaceVoiceBlob: boundedMocks.encode,
  startWorkspaceBoundedVoiceRecorder: boundedMocks.start,
}));

import { useWorkspaceVoiceInteractionController } from './WorkspaceVoiceInteractionController';

function Harness({
  submitVoiceTurn,
}: {
  submitVoiceTurn: WorkspaceInteractionTarget['submitVoiceTurn'];
}) {
  const target = React.useMemo<WorkspaceInteractionTarget>(() => ({
    targetId: 'chat:ws_test',
    targetKind: 'workspace_chat',
    targetLabel: 'Chat',
    revision: 'workspace_chat:r1',
    submissionPolicy: 'review_then_submit',
    freezeContext: () => ({ draft: '' }),
    submitVoiceTurn,
    realtimeTransport: {
      kind: 'meeting_realtime',
      handleCommandAccepted: vi.fn(),
    },
  }), [submitVoiceTurn]);
  useWorkspaceInteractionTargetRegistration(target);
  const controller = useWorkspaceVoiceInteractionController('http://api.test');
  return (
    <>
      <output data-testid="voice-state">{controller.state}</output>
      <output data-testid="voice-mode">{controller.mode}</output>
      <output data-testid="voice-inflight">{String(controller.turnInFlight)}</output>
      <button type="button" data-testid="voice-start" onClick={() => void controller.start()}>
        Start
      </button>
      <button type="button" data-testid="voice-stop" onClick={() => void controller.stop()}>
        Stop
      </button>
      <button type="button" data-testid="voice-realtime" onClick={() => controller.setMode('realtime')}>
        Realtime
      </button>
      <button type="button" data-testid="voice-cancel" onClick={controller.cancel}>
        Cancel
      </button>
    </>
  );
}

function recording() {
  return {
    audioBlob: new Blob(['wav-audio'], { type: 'audio/wav' }),
    mimeType: 'audio/wav' as const,
  };
}

describe('useWorkspaceVoiceInteractionController', () => {
  beforeEach(() => {
    boundedMocks.start.mockImplementation(async (
      input: NonNullable<typeof boundedMocks.input>,
    ) => {
      boundedMocks.input = input;
      return {
        state: 'recording',
        stop: vi.fn(),
        cancel: vi.fn(),
      };
    });
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn(async () => ({
          getTracks: () => [{ stop: vi.fn() }],
        })),
      },
    });
  });

  afterEach(() => {
    boundedMocks.input = null;
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it('is idle until explicit start, requests aligned mic constraints, and submits one WAV turn', async () => {
    const submitVoiceTurn = vi.fn(async () => ({
      status: 'draft_updated' as const,
      transcript: 'hello',
    }));
    render(
      <WorkspaceInteractionIngressProvider workspaceId="ws_test">
        <Harness submitVoiceTurn={submitVoiceTurn} />
      </WorkspaceInteractionIngressProvider>,
    );

    expect(screen.getByTestId('voice-state')).toHaveTextContent('idle');
    fireEvent.click(screen.getByTestId('voice-start'));
    await waitFor(() => expect(screen.getByTestId('voice-state')).toHaveTextContent('recording'));
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        autoGainControl: true,
        noiseSuppression: true,
      },
    });
    fireEvent.click(screen.getByTestId('voice-stop'));
    expect(screen.getByTestId('voice-inflight')).toHaveTextContent('true');

    await act(async () => {
      await boundedMocks.input?.onComplete(recording());
    });
    expect(screen.getByTestId('voice-state')).toHaveTextContent('draft_updated');
    expect(submitVoiceTurn).toHaveBeenCalledTimes(1);
    expect(submitVoiceTurn.mock.calls[0][0]).toMatchObject({
      audioBase64: 'encoded-audio',
      mimeType: 'audio/wav',
      language: 'auto',
    });
  });

  it('returns empty without submitting when the PCM facade has no frames', async () => {
    const submitVoiceTurn = vi.fn();
    render(
      <WorkspaceInteractionIngressProvider workspaceId="ws_test">
        <Harness submitVoiceTurn={submitVoiceTurn} />
      </WorkspaceInteractionIngressProvider>,
    );
    fireEvent.click(screen.getByTestId('voice-start'));
    await waitFor(() => expect(screen.getByTestId('voice-state')).toHaveTextContent('recording'));
    fireEvent.click(screen.getByTestId('voice-stop'));

    await act(async () => {
      await boundedMocks.input?.onComplete(null);
    });
    expect(screen.getByTestId('voice-state')).toHaveTextContent('empty');
    expect(submitVoiceTurn).not.toHaveBeenCalled();
  });

  it('locks mode, cancel, and a second start until the bounded submit is terminal', async () => {
    let resolveSubmit: ((value: { status: 'draft_updated'; transcript: string }) => void) | null = null;
    const submitVoiceTurn = vi.fn(() => new Promise<{
      status: 'draft_updated';
      transcript: string;
    }>((resolve) => {
      resolveSubmit = resolve;
    }));
    render(
      <WorkspaceInteractionIngressProvider workspaceId="ws_test">
        <Harness submitVoiceTurn={submitVoiceTurn} />
      </WorkspaceInteractionIngressProvider>,
    );
    fireEvent.click(screen.getByTestId('voice-start'));
    await waitFor(() => expect(screen.getByTestId('voice-state')).toHaveTextContent('recording'));
    fireEvent.click(screen.getByTestId('voice-stop'));
    expect(screen.getByTestId('voice-inflight')).toHaveTextContent('true');

    let completion: Promise<void> | undefined;
    await act(async () => {
      completion = boundedMocks.input?.onComplete(recording());
      await Promise.resolve();
    });
    await waitFor(() => expect(screen.getByTestId('voice-inflight')).toHaveTextContent('true'));
    fireEvent.click(screen.getByTestId('voice-realtime'));
    fireEvent.click(screen.getByTestId('voice-cancel'));
    fireEvent.click(screen.getByTestId('voice-start'));

    expect(screen.getByTestId('voice-mode')).toHaveTextContent('bounded');
    expect(screen.getByTestId('voice-state')).toHaveTextContent('transcribing');
    expect(boundedMocks.start).toHaveBeenCalledTimes(1);
    expect(submitVoiceTurn).toHaveBeenCalledTimes(1);

    resolveSubmit?.({ status: 'draft_updated', transcript: 'done' });
    await act(async () => {
      await completion;
    });
    expect(screen.getByTestId('voice-inflight')).toHaveTextContent('false');
    fireEvent.click(screen.getByTestId('voice-realtime'));
    expect(screen.getByTestId('voice-mode')).toHaveTextContent('realtime');
  });
});
