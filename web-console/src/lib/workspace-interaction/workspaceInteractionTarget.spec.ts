import { describe, expect, it, vi } from 'vitest';

import {
  freezeWorkspaceInteractionTarget,
  workspaceInteractionFingerprint,
  workspaceInteractionRevision,
  type WorkspaceInteractionTarget,
} from './workspaceInteractionTarget';

function buildTarget(): WorkspaceInteractionTarget {
  return {
    targetId: 'meeting:1',
    targetKind: 'meeting_command',
    targetLabel: 'Meeting',
    revision: workspaceInteractionRevision('meeting_command', {
      meeting_id: 'mtg_1',
      graph: { selection_hash: 'gsel_1' },
    }),
    submissionPolicy: 'direct_submit',
    freezeContext: () => ({
      meeting_id: 'mtg_1',
      graph: { selection_hash: 'gsel_1' },
      mentions: [{ token: '@ig' }],
    }),
    submitVoiceTurn: vi.fn(),
  };
}

describe('workspaceInteractionTarget', () => {
  it('produces order-stable fingerprints and semantic revisions', () => {
    expect(workspaceInteractionFingerprint({
      b: 2,
      a: { d: 4, c: 3 },
    })).toBe(workspaceInteractionFingerprint({
      a: { c: 3, d: 4 },
      b: 2,
    }));
    expect(workspaceInteractionRevision('workspace_chat', { draft: 'a' }))
      .not.toBe(workspaceInteractionRevision('workspace_chat', { draft: 'b' }));
  });

  it('deep-freezes a detached context snapshot', () => {
    const frozen = freezeWorkspaceInteractionTarget('ws_1', buildTarget());
    expect(frozen.workspaceId).toBe('ws_1');
    expect(frozen.targetKind).toBe('meeting_command');
    expect(frozen.contextHash).toMatch(/^fnv1a32:/);
    expect(Object.isFrozen(frozen)).toBe(true);
    expect(Object.isFrozen(frozen.context)).toBe(true);
    expect(Object.isFrozen(frozen.context.graph)).toBe(true);
    expect(Object.isFrozen(frozen.context.mentions)).toBe(true);
  });
});
