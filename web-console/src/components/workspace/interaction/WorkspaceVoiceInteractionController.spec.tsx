import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  WorkspaceInteractionIngressProvider,
  useWorkspaceInteractionTargetRegistration,
} from '@/lib/workspace-interaction/WorkspaceInteractionIngressProvider';
import type { WorkspaceInteractionTarget } from '@/lib/workspace-interaction/workspaceInteractionTarget';

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
  }), [submitVoiceTurn]);
  useWorkspaceInteractionTargetRegistration(target);
  const controller = useWorkspaceVoiceInteractionController('http://api.test');
  return (
    <>
      <output data-testid="voice-state">{controller.state}</output>
      <button type="button" data-testid="voice-start" onClick={() => void controller.start()}>
        Start
      </button>
      <button type="button" data-testid="voice-stop" onClick={() => void controller.stop()}>
        Stop
      </button>
    </>
  );
}

describe('useWorkspaceVoiceInteractionController', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('is idle with zero capture requests, then submits one bounded frozen turn', async () => {
    const trackStop = vi.fn();
    const getUserMedia = vi.fn(async () => ({
      getTracks: () => [{ stop: trackStop }],
    }));
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia },
    });
    const recorders: FakeMediaRecorder[] = [];
    class FakeMediaRecorder {
      static isTypeSupported(value: string) {
        return value === 'audio/webm;codecs=opus';
      }
      state: RecordingState = 'inactive';
      mimeType: string;
      ondataavailable: ((event: BlobEvent) => void) | null = null;
      onstop: (() => void) | null = null;
      constructor(_stream: MediaStream, options?: MediaRecorderOptions) {
        this.mimeType = options?.mimeType || 'audio/webm';
        recorders.push(this);
      }
      start() {
        this.state = 'recording';
      }
      stop() {
        this.state = 'inactive';
        this.ondataavailable?.({
          data: new Blob(['audio'], { type: this.mimeType }),
        } as BlobEvent);
        this.onstop?.();
      }
    }
    vi.stubGlobal('MediaRecorder', FakeMediaRecorder);
    const submitVoiceTurn = vi.fn(async (
      _turn: Parameters<WorkspaceInteractionTarget['submitVoiceTurn']>[0],
      _snapshot: Parameters<WorkspaceInteractionTarget['submitVoiceTurn']>[1],
    ) => ({
      status: 'draft_updated' as const,
      transcript: 'hello',
    }));

    render(
      <WorkspaceInteractionIngressProvider workspaceId="ws_test">
        <Harness submitVoiceTurn={submitVoiceTurn} />
      </WorkspaceInteractionIngressProvider>,
    );
    expect(screen.getByTestId('voice-state')).toHaveTextContent('idle');
    expect(getUserMedia).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('voice-start'));
    await waitFor(() => {
      expect(screen.getByTestId('voice-state')).toHaveTextContent('recording');
    });
    expect(recorders).toHaveLength(1);

    fireEvent.click(screen.getByTestId('voice-stop'));
    await waitFor(() => {
      expect(screen.getByTestId('voice-state')).toHaveTextContent('draft_updated');
    });
    expect(submitVoiceTurn).toHaveBeenCalledTimes(1);
    expect(submitVoiceTurn.mock.calls[0][0]).toMatchObject({
      mimeType: 'audio/webm;codecs=opus',
      language: 'auto',
    });
    expect(trackStop).toHaveBeenCalled();
  });
});
