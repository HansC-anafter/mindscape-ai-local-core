import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  WorkspaceInteractionIngressProvider,
  useWorkspaceInteractionIngress,
} from '@/lib/workspace-interaction/WorkspaceInteractionIngressProvider';
import { transcribeWorkspaceAudio } from '@/lib/workspace-interaction/workspaceSpeechToTextClient';

import { InputArea } from './InputArea';

const inputMocks = vi.hoisted(() => ({
  setInput: vi.fn(),
}));
const translate = vi.hoisted(() => (key: string) => key);

vi.mock('@/lib/i18n', () => ({
  useT: () => translate,
}));
vi.mock('@/contexts/UIStateContext', () => ({
  useUIState: () => ({
    input: '',
    setInput: inputMocks.setInput,
    llmConfigured: true,
    duplicateFileToast: null,
    copiedAll: false,
  }),
}));
vi.mock('@/contexts/WorkspaceRefsContext', () => ({
  useWorkspaceRefs: () => ({
    textareaRef: { current: null },
    fileInputRef: { current: null },
  }),
}));
vi.mock('@/contexts/MessagesContext', () => ({
  useMessages: () => ({ messages: [] }),
}));
vi.mock('@/hooks/useFileHandling', () => ({
  useFileHandling: () => ({
    uploadedFiles: [],
    analyzingFiles: new Set(),
    handleAnalyzeFile: vi.fn(),
    clearFiles: vi.fn(),
    isDragging: false,
    handleFileInputChange: vi.fn(),
    handleDragOver: vi.fn(),
    handleDragLeave: vi.fn(),
    handleDrop: vi.fn(),
    removeFile: vi.fn(),
  }),
}));
vi.mock('./FilePreviewGrid', () => ({
  FilePreviewGrid: () => null,
}));
vi.mock('./InputBottomBar', () => ({
  InputBottomBar: () => null,
}));
vi.mock('../../app/workspaces/components/IntentChips', () => ({
  default: () => null,
}));
vi.mock('./WorkspaceChatRuntimeControls', () => ({
  WorkspaceChatRuntimeControls: () => null,
}));
vi.mock('@/lib/workspace-interaction/workspaceSpeechToTextClient', () => ({
  transcribeWorkspaceAudio: vi.fn(async () => ({
    text: 'voice text',
    language: 'en',
  })),
}));

function VoiceDriver() {
  const ingress = useWorkspaceInteractionIngress();
  return (
    <button
      type="button"
      data-testid="workspace-chat-voice-driver"
      data-active-target={ingress.activeTarget?.targetKind || ''}
      onClick={async () => {
        const frozen = ingress.freezeActiveTarget();
        await ingress.submitFrozenVoiceTurn(frozen, {
          clientTurnId: 'turn_chat_1',
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

describe('InputArea workspace interaction target', () => {
  it('adds a transcript to the existing chat draft without submitting chat', async () => {
    inputMocks.setInput.mockClear();
    const onSend = vi.fn();
    render(
      <WorkspaceInteractionIngressProvider workspaceId="ws_chat">
        <InputArea
          workspaceId="ws_chat"
          apiUrl="http://api.test"
          onSend={onSend}
          isLoading={false}
          canSend
        />
        <VoiceDriver />
      </WorkspaceInteractionIngressProvider>,
    );

    fireEvent.focus(screen.getByRole('textbox'));
    await waitFor(() => {
      expect(screen.getByTestId('workspace-chat-voice-driver')).toHaveAttribute(
        'data-active-target',
        'workspace_chat',
      );
    });
    fireEvent.click(screen.getByTestId('workspace-chat-voice-driver'));
    await waitFor(() => {
      expect(inputMocks.setInput).toHaveBeenCalledWith('voice text');
    });

    expect(transcribeWorkspaceAudio).toHaveBeenCalledTimes(1);
    expect(onSend).not.toHaveBeenCalled();
  });
});
