'use client';

import React from 'react';

import { useKeyboardShortcuts } from '@/lib/keyboard-shortcuts';
import type { KeyboardShortcutOwnerType } from '@/lib/keyboard-shortcuts';

export const TOOL_RAIL_ACTIVE_PANEL_TOGGLE_COMMAND_ID = 'tool_rail.active_panel.toggle';
export const TOOL_RAIL_ACTIVE_PANEL_TOGGLE_SHORTCUT = '~';

interface ToolRailPanelToggleShortcutOptions {
  bindingId: string;
  scope: string;
  label: string;
  ownerType: KeyboardShortcutOwnerType;
  ownerId?: string;
  ownerLabel?: string;
  enabled: boolean;
  shortcutPriority?: number;
  onToggle: () => void;
}

export function useToolRailPanelToggleShortcut({
  bindingId,
  scope,
  label,
  ownerType,
  ownerId,
  ownerLabel,
  enabled,
  shortcutPriority,
  onToggle,
}: ToolRailPanelToggleShortcutOptions) {
  const { registerCommand } = useKeyboardShortcuts();

  React.useEffect(() => {
    if (!enabled) {
      return undefined;
    }
    return registerCommand({
      bindingId,
      commandId: TOOL_RAIL_ACTIVE_PANEL_TOGGLE_COMMAND_ID,
      label,
      ownerType,
      ownerId,
      ownerLabel,
      defaultShortcut: TOOL_RAIL_ACTIVE_PANEL_TOGGLE_SHORTCUT,
      scope,
      preventDefault: true,
      shortcutPriority,
      action: () => onToggle(),
    });
  }, [bindingId, enabled, label, onToggle, ownerId, ownerLabel, ownerType, registerCommand, scope, shortcutPriority]);
}
