import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { HostRuntimeComposer } from './HostRuntimeComposer';

vi.mock('./HostRuntimeVoicePromptButton', () => ({
  HostRuntimeVoicePromptButton: (props: any) => (
    <button
      type="button"
      data-testid="host-runtime-voice-prompt-button"
      data-workspace-id={props.workspaceId}
      data-meeting-id={props.meetingId || ''}
      onClick={() => props.onTranscript('voice prompt')}
    >
      Voice
    </button>
  ),
}));

describe('HostRuntimeComposer', () => {
  it('appends a voice transcript into the prompt and submits it through the host runtime surface', () => {
    const onSubmit = vi.fn();

    render(
      <HostRuntimeComposer
        apiUrl="http://api.test"
        workspaceId="ws_test"
        meetingId="mtg_test"
        disabled={false}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByTestId('host-runtime-voice-prompt-button')).toHaveAttribute(
      'data-workspace-id',
      'ws_test',
    );
    expect(screen.getByTestId('host-runtime-voice-prompt-button')).toHaveAttribute(
      'data-meeting-id',
      'mtg_test',
    );

    fireEvent.click(screen.getByTestId('host-runtime-voice-prompt-button'));
    expect(screen.getByTestId('host-runtime-prompt')).toHaveValue('voice prompt');

    fireEvent.click(screen.getByTestId('host-runtime-submit'));
    expect(onSubmit).toHaveBeenCalledWith('voice prompt');
    expect(screen.getByTestId('host-runtime-pinned-prompt')).toHaveTextContent('voice prompt');
    expect(screen.getByTestId('host-runtime-prompt')).toHaveValue('');
  });
});
