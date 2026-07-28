import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  WorkspaceInteractionIngressProvider,
  useWorkspaceInteractionIngress,
  useWorkspaceInteractionTargetRegistration,
} from '@/lib/workspace-interaction/WorkspaceInteractionIngressProvider';
import type { WorkspaceInteractionTarget } from '@/lib/workspace-interaction/workspaceInteractionTarget';
import { ensureWorkspaceVoiceMeetingSession } from '@/lib/workspace-interaction/workspaceVoiceMeetingBootstrapClient';

import {
  useWorkspaceVoiceMeetingBootstrap,
  WorkspaceVoiceMeetingBootstrapProvider,
} from './WorkspaceVoiceMeetingBootstrapProvider';

const railState = vi.hoisted(() => ({
  activeCapabilityCode: 'yogacoach' as string | null,
}));

vi.mock('@/app/workspaces/[workspaceId]/components/useWorkspaceGlobalToolRail', () => ({
  useOptionalWorkspaceGlobalToolRail: () => ({
    activeCapabilityCode: railState.activeCapabilityCode,
  }),
}));
vi.mock('@/lib/i18n', () => ({
  useT: () => (key: string) => key,
}));
vi.mock(
  '@/lib/workspace-interaction/workspaceVoiceMeetingBootstrapClient',
  async (importOriginal) => {
    const actual = await importOriginal<
      typeof import('@/lib/workspace-interaction/workspaceVoiceMeetingBootstrapClient')
    >();
    return {
      ...actual,
      ensureWorkspaceVoiceMeetingSession: vi.fn(),
    };
  },
);

function BootstrapProbe() {
  const bootstrap = useWorkspaceVoiceMeetingBootstrap();
  const ingress = useWorkspaceInteractionIngress();
  return (
    <>
      <button
        type="button"
        onClick={() => {
          void bootstrap.ensureMeetingTarget();
          void bootstrap.ensureMeetingTarget();
        }}
      >
        bootstrap
      </button>
      <div data-testid="bootstrap-status">{bootstrap.status}</div>
      <div data-testid="target-count">{ingress.targets.length}</div>
      <div data-testid="active-target">{ingress.activeTarget?.targetLabel || ''}</div>
    </>
  );
}

function ExistingTargetRegistration() {
  const target = React.useMemo<WorkspaceInteractionTarget>(() => ({
    targetId: 'chat:ws_1',
    targetKind: 'workspace_chat',
    targetLabel: 'Existing chat',
    revision: 'r1',
    submissionPolicy: 'review_then_submit',
    freezeContext: () => ({}),
    submitVoiceTurn: async () => ({ status: 'draft_updated' }),
  }), []);
  useWorkspaceInteractionTargetRegistration(target);
  return null;
}

function renderProvider(children?: React.ReactNode) {
  return render(
    <WorkspaceInteractionIngressProvider workspaceId="ws_1">
      <WorkspaceVoiceMeetingBootstrapProvider
        apiUrl="http://api.test"
        workspaceId="ws_1"
      >
        {children}
        <BootstrapProbe />
      </WorkspaceVoiceMeetingBootstrapProvider>
    </WorkspaceInteractionIngressProvider>,
  );
}

describe('WorkspaceVoiceMeetingBootstrapProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    railState.activeCapabilityCode = 'yogacoach';
    vi.mocked(ensureWorkspaceVoiceMeetingSession).mockResolvedValue({
      id: 'meeting_voice_1',
      workspace_id: 'ws_1',
      project_id: 'workspace_voice',
      thread_id: 'workspace_voice_yogacoach',
      status: 'active',
      is_active: true,
      metadata: {
        active_pack_code: 'yogacoach',
      },
    });
  });

  it('singleflights concurrent bootstrap requests and registers one persistent target', async () => {
    renderProvider();

    fireEvent.click(screen.getByRole('button', { name: 'bootstrap' }));

    await waitFor(() => {
      expect(screen.getByTestId('bootstrap-status').textContent).toBe('ready');
      expect(screen.getByTestId('target-count').textContent).toBe('1');
    });
    expect(ensureWorkspaceVoiceMeetingSession).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('active-target').textContent).toBe(
      'workspaceVoiceTargetWorkspaceMeeting',
    );
  });

  it('preserves an existing active target without creating a background Meeting', async () => {
    renderProvider(<ExistingTargetRegistration />);
    await waitFor(() => {
      expect(screen.getByTestId('active-target').textContent).toBe('Existing chat');
    });

    fireEvent.click(screen.getByRole('button', { name: 'bootstrap' }));

    await waitFor(() => {
      expect(screen.getByTestId('target-count').textContent).toBe('1');
    });
    expect(ensureWorkspaceVoiceMeetingSession).not.toHaveBeenCalled();
    expect(screen.getByTestId('active-target').textContent).toBe('Existing chat');
  });
});
