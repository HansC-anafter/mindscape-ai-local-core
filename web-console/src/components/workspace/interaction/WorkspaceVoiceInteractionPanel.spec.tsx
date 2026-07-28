import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { WorkspaceVoiceInteractionPanel } from './WorkspaceVoiceInteractionPanel';

const panelState = vi.hoisted(() => ({
  targets: [] as unknown[],
  bootstrapStatus: 'starting',
  bootstrapError: null as string | null,
  ensureMeetingTarget: vi.fn(),
  controller: {
    activeTarget: null as null | Record<string, unknown>,
    mode: 'bounded',
    state: 'idle',
    error: null as string | null,
    transcript: null as string | null,
    answerText: null as string | null,
    realtimeAvailable: false,
    setMode: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
    cancel: vi.fn(),
    interruptRealtime: vi.fn(),
  },
}));

vi.mock('@/lib/i18n', () => ({
  useT: () => (key: string) => key,
}));
vi.mock('@/lib/workspace-interaction/WorkspaceInteractionIngressProvider', () => ({
  useWorkspaceInteractionIngress: () => ({
    targets: panelState.targets,
  }),
}));
vi.mock('./WorkspaceVoiceMeetingBootstrapProvider', () => ({
  useWorkspaceVoiceMeetingBootstrap: () => ({
    status: panelState.bootstrapStatus,
    error: panelState.bootstrapError,
    ensureMeetingTarget: panelState.ensureMeetingTarget,
  }),
}));
vi.mock('./WorkspaceVoiceInteractionController', () => ({
  useWorkspaceVoiceInteractionController: () => panelState.controller,
}));

describe('WorkspaceVoiceInteractionPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    panelState.targets = [];
    panelState.bootstrapStatus = 'starting';
    panelState.controller.activeTarget = null;
    panelState.controller.state = 'idle';
    panelState.controller.transcript = null;
    panelState.controller.answerText = null;
  });

  it('shows background Meeting bootstrap progress instead of a text-focus downgrade', () => {
    render(<WorkspaceVoiceInteractionPanel apiUrl="http://api.test" />);

    expect(
      screen.getByTestId('workspace-voice-meeting-bootstrap-starting'),
    ).toHaveTextContent('workspaceVoiceMeetingBootstrapStarting');
    expect(screen.getByTestId('workspace-voice-primary-control')).toBeDisabled();
  });

  it('shows a grounded semantic answer while keeping the Meeting target active', () => {
    panelState.targets = [{}];
    panelState.bootstrapStatus = 'ready';
    panelState.controller.activeTarget = {
      targetLabel: 'Workspace Meeting Engine',
      submissionPolicy: 'direct_submit',
      realtimeTransport: {},
    };
    panelState.controller.state = 'answered';
    panelState.controller.transcript = 'How should I align?';
    panelState.controller.answerText = 'Keep the knee tracking over the second toe.';

    render(<WorkspaceVoiceInteractionPanel apiUrl="http://api.test" />);

    expect(screen.getByTestId('workspace-voice-answer')).toHaveTextContent(
      'Keep the knee tracking over the second toe.',
    );
    expect(screen.getByTestId('workspace-voice-primary-control')).toBeEnabled();
  });
});
