import { describe, expect, it } from 'vitest';

import { resolveKeyboardShortcut } from './shortcut-resolver';
import type { KeyboardShortcutCommand, KeyboardShortcutProfile } from './shortcut-types';

const emptyProfile: KeyboardShortcutProfile = {
  schema_version: 1,
  bindings: [],
};

const baseCommand: KeyboardShortcutCommand = {
  bindingId: 'workspace_tool:ig:feed_grid_card_load_limit:open',
  commandId: 'pack.workspace_tool.open',
  label: 'Feed Load',
  ownerType: 'pack',
  ownerId: 'ig',
  defaultShortcut: 'F9',
  scope: 'workbench:ws:ig',
};

describe('keyboard shortcut resolver', () => {
  it('matches active scoped commands', () => {
    const event = new KeyboardEvent('keydown', { key: 'F9' });
    const result = resolveKeyboardShortcut({
      commands: [baseCommand],
      profile: emptyProfile,
      activeScopes: new Set(['global', 'workbench:ws:ig']),
      event,
    });

    expect(result.status).toBe('matched');
    if (result.status === 'matched') {
      expect(result.command.bindingId).toBe(baseCommand.bindingId);
    }
  });

  it('blocks editable targets by default', () => {
    const input = document.createElement('input');
    const event = new KeyboardEvent('keydown', { key: 'F9' });
    Object.defineProperty(event, 'target', { value: input });

    const result = resolveKeyboardShortcut({
      commands: [baseCommand],
      profile: emptyProfile,
      activeScopes: new Set(['global', 'workbench:ws:ig']),
      event,
    });

    expect(result).toMatchObject({ status: 'blocked', reason: 'editable-target' });
  });

  it('blocks same-scope conflicts', () => {
    const event = new KeyboardEvent('keydown', { key: 'F9' });
    const result = resolveKeyboardShortcut({
      commands: [
        baseCommand,
        { ...baseCommand, bindingId: 'workspace_tool:ig:seed_following_crawl:open', label: 'Seed' },
      ],
      profile: emptyProfile,
      activeScopes: new Set(['global', 'workbench:ws:ig']),
      event,
    });

    expect(result).toMatchObject({ status: 'blocked', reason: 'conflict' });
  });

  it('prefers explicit active-panel priority over static scope priority', () => {
    const event = new KeyboardEvent('keydown', { key: '`', code: 'Backquote' });
    const workspacePanelCommand: KeyboardShortcutCommand = {
      bindingId: 'tool_rail:workspace:active_panel:toggle',
      commandId: 'tool_rail.active_panel.toggle',
      label: 'Toggle active workspace tool panel',
      ownerType: 'core',
      defaultShortcut: '~',
      scope: 'workspace:ws',
      shortcutPriority: 350,
    };
    const packPanelCommand: KeyboardShortcutCommand = {
      bindingId: 'tool_rail:workbench:ig:active_panel:toggle',
      commandId: 'tool_rail.active_panel.toggle',
      label: 'Toggle active tool panel',
      ownerType: 'pack',
      ownerId: 'ig',
      defaultShortcut: '~',
      scope: 'workbench:ws:ig',
    };

    const result = resolveKeyboardShortcut({
      commands: [workspacePanelCommand, packPanelCommand],
      profile: emptyProfile,
      activeScopes: new Set(['global', 'workspace:ws', 'workbench:ws:ig']),
      event,
    });

    expect(result.status).toBe('matched');
    if (result.status === 'matched') {
      expect(result.command.bindingId).toBe('tool_rail:workspace:active_panel:toggle');
    }
  });

  it('honors persisted disables', () => {
    const event = new KeyboardEvent('keydown', { key: 'F9' });
    const result = resolveKeyboardShortcut({
      commands: [baseCommand],
      profile: {
        schema_version: 1,
        bindings: [
          {
            binding_id: baseCommand.bindingId,
            command_id: baseCommand.commandId,
            owner_type: 'pack',
            owner_id: 'ig',
            disabled: true,
          },
        ],
      },
      activeScopes: new Set(['global', 'workbench:ws:ig']),
      event,
    });

    expect(result).toMatchObject({ status: 'blocked', reason: 'no-match' });
  });
});
