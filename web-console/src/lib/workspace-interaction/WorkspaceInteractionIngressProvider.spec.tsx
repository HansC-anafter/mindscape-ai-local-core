import React from 'react';
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  WorkspaceInteractionIngressProvider,
  useWorkspaceInteractionIngress,
} from './WorkspaceInteractionIngressProvider';
import {
  WorkspaceInteractionTargetError,
  type WorkspaceInteractionTarget,
} from './workspaceInteractionTarget';

function target(
  targetId: string,
  revision: string,
  submitVoiceTurn: WorkspaceInteractionTarget['submitVoiceTurn'] = vi.fn(
    async () => ({ status: 'draft_updated' as const }),
  ),
): WorkspaceInteractionTarget {
  return {
    targetId,
    targetKind: 'workspace_chat',
    targetLabel: targetId,
    revision,
    submissionPolicy: 'review_then_submit',
    freezeContext: () => ({ target_id: targetId }),
    submitVoiceTurn,
  };
}

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <WorkspaceInteractionIngressProvider workspaceId="ws_test">
      {children}
    </WorkspaceInteractionIngressProvider>
  );
}

describe('WorkspaceInteractionIngressProvider', () => {
  it('auto-activates one target and requires explicit activation for multiple targets', () => {
    const { result } = renderHook(useWorkspaceInteractionIngress, { wrapper });
    let disposeFirst = () => {};
    let disposeSecond = () => {};

    act(() => {
      disposeFirst = result.current.registerTarget('scope:chat', target('chat', 'r1'));
    });
    expect(result.current.activeTarget?.targetId).toBe('chat');

    act(() => {
      disposeSecond = result.current.registerTarget('scope:meeting', target('meeting', 'r1'));
    });
    expect(result.current.activeTarget).toBeNull();
    expect(() => result.current.freezeActiveTarget()).toThrowError(
      expect.objectContaining({ code: 'ambiguous_target' }),
    );

    act(() => {
      result.current.activateTarget('meeting', 'explicit_terminal_focus');
    });
    expect(result.current.activeTarget?.targetId).toBe('meeting');

    act(() => {
      disposeFirst();
      disposeSecond();
    });
  });

  it('fails closed when a frozen target is replaced with a new revision', async () => {
    const submitVoiceTurn = vi.fn(async () => ({ status: 'draft_updated' as const }));
    const { result } = renderHook(useWorkspaceInteractionIngress, { wrapper });
    let dispose = () => {};

    act(() => {
      dispose = result.current.registerTarget(
        'scope:chat',
        target('chat', 'r1', submitVoiceTurn),
      );
    });
    const frozen = result.current.freezeActiveTarget();
    act(() => {
      result.current.registerTarget(
        'scope:chat',
        target('chat', 'r2', submitVoiceTurn),
      );
    });

    await expect(result.current.submitFrozenVoiceTurn(frozen, {
      clientTurnId: 'turn-1',
      audioBase64: 'YXVkaW8=',
      mimeType: 'audio/webm',
      language: 'auto',
    })).rejects.toEqual(expect.objectContaining({ code: 'stale_target' }));
    expect(submitVoiceTurn).not.toHaveBeenCalled();

    act(() => dispose());
  });

  it('submits once through the current frozen target without side effects on mount', async () => {
    const submitVoiceTurn = vi.fn(async () => ({ status: 'submitted' as const }));
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const { result } = renderHook(useWorkspaceInteractionIngress, { wrapper });

    act(() => {
      result.current.registerTarget(
        'scope:meeting',
        target('meeting', 'r1', submitVoiceTurn),
      );
    });
    const frozen = result.current.freezeActiveTarget();
    await result.current.submitFrozenVoiceTurn(frozen, {
      clientTurnId: 'turn-1',
      audioBase64: 'YXVkaW8=',
      mimeType: 'audio/webm',
      language: 'auto',
    });

    expect(submitVoiceTurn).toHaveBeenCalledTimes(1);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it('returns a typed no-target error', () => {
    const { result } = renderHook(useWorkspaceInteractionIngress, { wrapper });
    try {
      result.current.freezeActiveTarget();
      throw new Error('expected error');
    } catch (error) {
      expect(error).toBeInstanceOf(WorkspaceInteractionTargetError);
      expect((error as WorkspaceInteractionTargetError).code).toBe('no_active_target');
    }
  });

  it('rejects a frozen snapshot from another workspace before submission', async () => {
    const submitVoiceTurn = vi.fn(async () => ({ status: 'submitted' as const }));
    const { result } = renderHook(useWorkspaceInteractionIngress, { wrapper });
    act(() => {
      result.current.registerTarget(
        'scope:meeting',
        target('meeting', 'r1', submitVoiceTurn),
      );
    });
    const frozen = {
      ...result.current.freezeActiveTarget(),
      workspaceId: 'ws_other',
    };

    await expect(result.current.submitFrozenVoiceTurn(frozen, {
      clientTurnId: 'turn_cross_workspace',
      audioBase64: 'YXVkaW8=',
      mimeType: 'audio/webm',
      language: 'auto',
    })).rejects.toEqual(expect.objectContaining({ code: 'workspace_mismatch' }));
    expect(submitVoiceTurn).not.toHaveBeenCalled();
  });
});
