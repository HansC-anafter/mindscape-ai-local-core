import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  WorkspaceInteractionIngressProvider,
  useWorkspaceInteractionIngress,
} from '@/lib/workspace-interaction/WorkspaceInteractionIngressProvider';
import { transcribeWorkspaceAudio } from '@/lib/workspace-interaction/workspaceSpeechToTextClient';

import { HostRuntimeComposer } from './HostRuntimeComposer';

const translate = vi.hoisted(() => (key: string) => key);

vi.mock('@/lib/i18n', () => ({
  useT: () => translate,
}));
vi.mock('@/lib/workspace-interaction/workspaceSpeechToTextClient', () => ({
  transcribeWorkspaceAudio: vi.fn(async () => ({
    text: 'voice prompt',
    language: 'en',
  })),
}));

function VoiceTargetDriver() {
  const ingress = useWorkspaceInteractionIngress();
  return (
    <button
      type="button"
      data-testid="submit-host-voice-turn"
      data-active-target={ingress.activeTarget?.targetKind || ''}
      onClick={async () => {
        const frozen = ingress.freezeActiveTarget();
        await ingress.submitFrozenVoiceTurn(frozen, {
          clientTurnId: 'turn_host_1',
          audioBase64: 'YXVkaW8=',
          mimeType: 'audio/webm',
          language: 'auto',
        });
      }}
    >
      Voice
    </button>
  );
}

describe('HostRuntimeComposer', () => {
  it('uses the registered review target to update the same draft, then submits once', async () => {
    const onSubmit = vi.fn();

    render(
      <WorkspaceInteractionIngressProvider workspaceId="ws_test">
        <HostRuntimeComposer
          apiUrl="http://api.test"
          workspaceId="ws_test"
          meetingId="mtg_test"
          sessionId="session_test"
          selectedObjectRef={null}
          graphContext={null}
          disabled={false}
          onSubmit={onSubmit}
        />
        <VoiceTargetDriver />
      </WorkspaceInteractionIngressProvider>,
    );

    fireEvent.focus(screen.getByTestId('host-runtime-prompt'));
    await waitFor(() => {
      expect(screen.getByTestId('submit-host-voice-turn')).toHaveAttribute(
        'data-active-target',
        'host_runtime_prompt',
      );
    });

    fireEvent.click(screen.getByTestId('submit-host-voice-turn'));
    await waitFor(() => {
      expect(screen.getByTestId('host-runtime-prompt')).toHaveValue('voice prompt');
    });
    expect(transcribeWorkspaceAudio).toHaveBeenCalledTimes(1);
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('host-runtime-submit'));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledWith('voice prompt');
    expect(screen.getByTestId('host-runtime-pinned-prompt')).toHaveTextContent(
      'voice prompt',
    );
    expect(screen.getByTestId('host-runtime-prompt')).toHaveValue('');
  });
});
