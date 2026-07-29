import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { KeyboardShortcutProvider } from '@/lib/keyboard-shortcuts';
import { loadLocalizedCapabilityUiComponent } from '@/lib/localized-capability-ui-component-loader';
import type { WorkspaceToolDefinition } from '@/lib/workspace-tools/workspace-tool-registry';
import { PackScopeToolRailHost } from './PackScopeToolRailHost';
import {
  PACK_SCOPE_TOOL_CLOSE_EVENT,
  PACK_SCOPE_TOOL_OPEN_EVENT,
} from './packScopeToolEvents';
import {
  createAolHost,
  feedLoadTool,
} from './PackScopeToolRailHost.test-support';

vi.mock('@/lib/capability-ui-localization', () => ({
  useOptionalCapabilityLocalization: () => ({ requestedLocale: 'zh-TW' }),
}));

vi.mock('@/lib/localized-capability-ui-component-loader', async () => {
  const ReactModule = await import('react');
  return {
    loadLocalizedCapabilityUiComponent: vi.fn(async () => ({
      localization: {
        requestedLocale: 'zh-TW',
        t: (key: string) => key,
      },
      Component: function LoadedPackToolPanel({
        workspaceId,
        apiUrl,
        tool,
      }: {
        workspaceId: string;
        apiUrl: string;
        tool: WorkspaceToolDefinition;
      }) {
        return ReactModule.createElement(
          'div',
          { 'data-testid': 'loaded-pack-tool-panel' },
          `${tool.id}:${workspaceId}:${apiUrl}`,
        );
      },
    })),
  };
});

describe('PackScopeToolRailHost events', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it('opens a requested tool by tool id and can hide the navigation toggle when no navigation is present', async () => {
    render(
      <KeyboardShortcutProvider loadProfileOnMount={false}>
        <PackScopeToolRailHost
          workspaceId="ws_test"
          capabilityCode="ig"
          apiUrl="http://api.test"
          tools={[feedLoadTool]}
          navigationEnabled={false}
          navigationCollapsed
          aolHost={createAolHost(vi.fn())}
          onNavigationCollapsedChange={vi.fn()}
        />
      </KeyboardShortcutProvider>,
    );

    expect(screen.queryByTestId('pack-scope-navigation-toggle')).toBeNull();

    await act(async () => {
      window.dispatchEvent(new CustomEvent(PACK_SCOPE_TOOL_OPEN_EVENT, {
        detail: {
          capabilityCode: 'ig',
          toolId: 'feed_grid_card_load_limit',
        },
      }));
    });

    await waitFor(() => {
      expect(loadLocalizedCapabilityUiComponent).toHaveBeenCalledWith({
        apiUrl: 'http://api.test',
        capabilityCode: 'ig',
        componentCode: 'FeedGridLoadToolPanel',
        requestedLocale: 'zh-TW',
        workspaceId: 'ws_test',
      });
      expect(screen.getByTestId('loaded-pack-tool-panel')).toBeInTheDocument();
    });
  });

  it('closes a requested active tool by close event', async () => {
    render(
      <KeyboardShortcutProvider loadProfileOnMount={false}>
        <PackScopeToolRailHost
          workspaceId="ws_test"
          capabilityCode="ig"
          apiUrl="http://api.test"
          tools={[feedLoadTool]}
          navigationEnabled={false}
          navigationCollapsed
          aolHost={createAolHost(vi.fn())}
          onNavigationCollapsedChange={vi.fn()}
        />
      </KeyboardShortcutProvider>,
    );

    await act(async () => {
      window.dispatchEvent(new CustomEvent(PACK_SCOPE_TOOL_OPEN_EVENT, {
        detail: {
          capabilityCode: 'ig',
          toolId: 'feed_grid_card_load_limit',
        },
      }));
    });

    await waitFor(() => {
      expect(screen.getByTestId('loaded-pack-tool-panel')).toBeInTheDocument();
    });

    await act(async () => {
      window.dispatchEvent(new CustomEvent(PACK_SCOPE_TOOL_CLOSE_EVENT, {
        detail: {
          capabilityCode: 'ig',
          toolId: 'feed_grid_card_load_limit',
        },
      }));
    });

    expect(screen.queryByTestId('pack-scope-tool-panel')).not.toBeInTheDocument();
  });
});
