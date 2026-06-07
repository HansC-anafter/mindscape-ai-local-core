import { afterEach, describe, expect, it } from 'vitest';

import {
  WORKSPACE_READINESS_CACHE_MS,
  clearWorkspaceReadinessPolicyForTests,
  markWorkspaceReadinessAttempt,
  shouldRequestWorkspaceReadiness,
} from './workspace-readiness-policy';

afterEach(() => {
  clearWorkspaceReadinessPolicyForTests();
});

describe('workspace readiness policy', () => {
  it('allows the first readiness request for a workspace', () => {
    expect(shouldRequestWorkspaceReadiness('ws-1', { hasLocalSnapshot: false })).toBe(true);
  });

  it('blocks repeated background readiness requests while local data is fresh enough', () => {
    markWorkspaceReadinessAttempt('ws-1', 1_000);

    expect(
      shouldRequestWorkspaceReadiness('ws-1', {
        hasLocalSnapshot: true,
        nowMs: 1_000 + WORKSPACE_READINESS_CACHE_MS - 1,
      }),
    ).toBe(false);
  });

  it('allows background readiness requests after the cooldown expires', () => {
    markWorkspaceReadinessAttempt('ws-1', 1_000);

    expect(
      shouldRequestWorkspaceReadiness('ws-1', {
        hasLocalSnapshot: true,
        nowMs: 1_000 + WORKSPACE_READINESS_CACHE_MS,
      }),
    ).toBe(true);
  });

  it('allows manual refresh regardless of the cooldown', () => {
    markWorkspaceReadinessAttempt('ws-1', 1_000);

    expect(
      shouldRequestWorkspaceReadiness('ws-1', {
        force: true,
        hasLocalSnapshot: true,
        nowMs: 1_001,
      }),
    ).toBe(true);
  });

  it('does not request readiness for placeholder workspace ids', () => {
    expect(shouldRequestWorkspaceReadiness('new')).toBe(false);
    expect(shouldRequestWorkspaceReadiness(null)).toBe(false);
  });
});
