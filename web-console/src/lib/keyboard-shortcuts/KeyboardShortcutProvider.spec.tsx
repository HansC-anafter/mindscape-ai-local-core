import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  KeyboardShortcutProvider,
  useKeyboardShortcuts,
} from './KeyboardShortcutProvider';
import type { KeyboardShortcutProfile } from './shortcut-types';

class MockBroadcastChannel {
  static channels = new Map<string, Set<MockBroadcastChannel>>();

  readonly name: string;
  onmessage: ((event: MessageEvent) => void) | null = null;

  constructor(name: string) {
    this.name = name;
    const channels = MockBroadcastChannel.channels.get(name) || new Set<MockBroadcastChannel>();
    channels.add(this);
    MockBroadcastChannel.channels.set(name, channels);
  }

  postMessage(message: unknown) {
    MockBroadcastChannel.channels.get(this.name)?.forEach((channel) => {
      if (channel !== this) {
        channel.onmessage?.({ data: message } as MessageEvent);
      }
    });
  }

  close() {
    MockBroadcastChannel.channels.get(this.name)?.delete(this);
  }
}

const overrideProfile: KeyboardShortcutProfile = {
  schema_version: 1,
  bindings: [
    {
      binding_id: 'workspace_tool:ig:feed_grid_card_load_limit:open',
      command_id: 'pack.workspace_tool.open',
      owner_type: 'pack',
      owner_id: 'ig',
      shortcut: 'F',
      disabled: false,
    },
  ],
};

function ProfileProbe({
  testId,
  canUpdate = false,
}: {
  testId: string;
  canUpdate?: boolean;
}) {
  const { profile, setProfile } = useKeyboardShortcuts();
  const shortcut = profile.bindings[0]?.shortcut || 'empty';
  return (
    <button
      type="button"
      data-testid={testId}
      data-shortcut={shortcut}
      onClick={() => {
        if (canUpdate) {
          setProfile(overrideProfile);
        }
      }}
    >
      {shortcut}
    </button>
  );
}

describe('KeyboardShortcutProvider profile sync', () => {
  beforeEach(() => {
    MockBroadcastChannel.channels.clear();
    vi.stubGlobal('BroadcastChannel', MockBroadcastChannel);
    window.localStorage.clear();
    delete globalThis.MindscapeRuntimeKeyboardShortcuts;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete globalThis.MindscapeRuntimeKeyboardShortcuts;
  });

  it('broadcasts user-updated profiles to other mounted providers', async () => {
    render(
      <>
        <KeyboardShortcutProvider loadProfileOnMount={false}>
          <ProfileProbe testId="source-profile" canUpdate />
        </KeyboardShortcutProvider>
        <KeyboardShortcutProvider loadProfileOnMount={false}>
          <ProfileProbe testId="target-profile" />
        </KeyboardShortcutProvider>
      </>,
    );

    expect(screen.getByTestId('target-profile')).toHaveAttribute('data-shortcut', 'empty');

    fireEvent.click(screen.getByTestId('source-profile'));

    await waitFor(() => {
      expect(screen.getByTestId('target-profile')).toHaveAttribute('data-shortcut', 'F');
    });
  });

  it('exposes the host provider snapshot to runtime asset consumers without a shared context', async () => {
    render(
      <>
        <KeyboardShortcutProvider loadProfileOnMount={false}>
          <ProfileProbe testId="host-profile" canUpdate />
        </KeyboardShortcutProvider>
        <ProfileProbe testId="runtime-profile" />
      </>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('runtime-profile')).toHaveAttribute('data-shortcut', 'empty');
    });

    fireEvent.click(screen.getByTestId('host-profile'));

    await waitFor(() => {
      expect(screen.getByTestId('runtime-profile')).toHaveAttribute('data-shortcut', 'F');
    });
  });
});
