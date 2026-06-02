import { describe, expect, it } from 'vitest';

import {
  deriveWorkspaceExecutorRuntimeOptions,
  deriveWorkspaceExecutorRuntimeStatus,
} from './workspaceExecutorRuntimeViewModel';

describe('workspaceExecutorRuntimeViewModel', () => {
  it('keeps an offline workspace-bound runtime selectable', () => {
    const options = deriveWorkspaceExecutorRuntimeOptions(
      ['codex_cli'],
      'codex_cli',
      [
        {
          id: 'codex_cli',
          name: 'Codex CLI',
          status: 'unavailable',
          reason: 'no_ws_client',
        },
      ],
    );

    expect(options).toEqual([
      {
        id: 'codex_cli',
        label: 'Codex CLI (bound)',
        disabled: false,
        status: 'unavailable',
        reason: 'no_ws_client',
        isBound: true,
      },
    ]);

    expect(deriveWorkspaceExecutorRuntimeStatus(
      'codex_cli',
      ['codex_cli'],
      'codex_cli',
      [
        {
          id: 'codex_cli',
          name: 'Codex CLI',
          status: 'unavailable',
          reason: 'no_ws_client',
        },
      ],
    )).toEqual({
      runtimeId: 'codex_cli',
      name: 'Codex CLI',
      badgeLabel: 'bound',
      statusLabel: 'workspace-bound, bridge offline',
      reason: 'no_ws_client',
    });
  });

  it('disables unavailable runtimes that are not workspace-bound', () => {
    const options = deriveWorkspaceExecutorRuntimeOptions(
      [],
      null,
      [
        {
          id: 'openclaw',
          name: 'OpenClaw',
          status: 'unavailable',
          reason: 'not_configured',
        },
      ],
    );

    expect(options[0]).toMatchObject({
      id: 'openclaw',
      label: 'OpenClaw (unavailable)',
      disabled: true,
      isBound: false,
    });
  });

  it('creates a synthetic selectable option when a bound runtime is missing from the agent snapshot', () => {
    const options = deriveWorkspaceExecutorRuntimeOptions(['codex_cli'], 'codex_cli', []);

    expect(options).toEqual([
      {
        id: 'codex_cli',
        label: 'codex_cli (bound)',
        disabled: false,
        status: 'unavailable',
        reason: null,
        isBound: true,
      },
    ]);
  });
});
