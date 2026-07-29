import React from 'react';
import { render, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  WorkspaceInteractionIngressProvider,
  useWorkspaceInteractionTargetRegistration,
} from '@/lib/workspace-interaction/WorkspaceInteractionIngressProvider';
import type { WorkspaceInteractionTarget } from '@/lib/workspace-interaction/workspaceInteractionTarget';

import { WorkspaceVoiceInteractionToolRegistration } from './WorkspaceVoiceInteractionToolRegistration';

const contributionSpy = vi.hoisted(() => vi.fn());
const translate = vi.hoisted(() => (key: string) => key);

vi.mock('@/app/workspaces/[workspaceId]/components/useWorkspaceGlobalToolRail', () => ({
  useWorkspaceGlobalToolContributions: contributionSpy,
}));
vi.mock('@/lib/i18n', () => ({
  useT: () => translate,
}));
vi.mock('./WorkspaceVoiceInteractionPanel', () => ({
  WorkspaceVoiceInteractionPanel: () => <div>Panel</div>,
}));

function TargetRegistration() {
  const target = React.useMemo<WorkspaceInteractionTarget>(() => ({
    targetId: 'chat:ws_test',
    targetKind: 'workspace_chat',
    targetLabel: 'Chat',
    revision: 'r1',
    submissionPolicy: 'review_then_submit',
    freezeContext: () => ({}),
    submitVoiceTurn: async () => ({ status: 'draft_updated' }),
  }), []);
  useWorkspaceInteractionTargetRegistration(target);
  return null;
}

describe('WorkspaceVoiceInteractionToolRegistration', () => {
  it('registers one stable runtime contribution and disables it without a target', async () => {
    contributionSpy.mockClear();
    render(
      <WorkspaceInteractionIngressProvider workspaceId="ws_test">
        <WorkspaceVoiceInteractionToolRegistration apiUrl="http://api.test" />
      </WorkspaceInteractionIngressProvider>,
    );
    await waitFor(() => expect(contributionSpy).toHaveBeenCalled());
    const [, contributions] = contributionSpy.mock.calls.at(-1) || [];
    expect(contributions).toHaveLength(1);
    expect(contributions[0]).toMatchObject({
      key: 'aol:voice',
      id: 'aol:voice',
      group: 'runtime',
      order: 25,
      visible: true,
      disabled: true,
      testId: 'workspace-voice-tool',
    });
  });

  it('enables the same contribution when a terminal target is registered', async () => {
    contributionSpy.mockClear();
    render(
      <WorkspaceInteractionIngressProvider workspaceId="ws_test">
        <TargetRegistration />
        <WorkspaceVoiceInteractionToolRegistration apiUrl="http://api.test" />
      </WorkspaceInteractionIngressProvider>,
    );
    await waitFor(() => {
      const [, contributions] = contributionSpy.mock.calls.at(-1) || [];
      expect(contributions[0].disabled).toBe(false);
    });
  });
});
