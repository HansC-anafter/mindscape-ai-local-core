import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { HostRuntimeComposer } from './HostRuntimeComposer';

vi.mock('./HostRuntimeVoicePromptButton', () => ({
  HostRuntimeVoicePromptButton: ({
    onTranscript,
  }: {
    apiUrl: string;
    disabled?: boolean;
    onTranscript: (transcript: string) => void;
  }) => (
    <button
      type="button"
      data-testid="host-runtime-voice-prompt-button"
      onClick={() => onTranscript('voice prompt')}
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
        disabled={false}
        onSubmit={onSubmit}
      />,
    );

    fireEvent.click(screen.getByTestId('host-runtime-voice-prompt-button'));
    expect(screen.getByTestId('host-runtime-prompt')).toHaveValue('voice prompt');

    fireEvent.click(screen.getByTestId('host-runtime-submit'));
    expect(onSubmit).toHaveBeenCalledWith('voice prompt');
  });
});
