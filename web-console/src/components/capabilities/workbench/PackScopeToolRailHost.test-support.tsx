import React from 'react';
import { vi } from 'vitest';

import { useKeyboardShortcuts } from '@/lib/keyboard-shortcuts';
import type {
  AddressableObjectHostBridge,
  AddressableSelectionTarget,
} from '@/lib/addressable-object-layer';
import type { KeyboardShortcutProfile } from '@/lib/keyboard-shortcuts';
import type { WorkspaceToolDefinition } from '@/lib/workspace-tools/workspace-tool-registry';

export const feedLoadTool: WorkspaceToolDefinition = {
  tool_key: 'ig:feed_grid_card_load_limit',
  capability_code: 'ig',
  id: 'feed_grid_card_load_limit',
  group: 'capability',
  slot: 'workbench.left_tool_rail',
  label: 'Feed Load',
  icon: 'SlidersHorizontal',
  order: 10,
  shortcut: 'F9',
  panel_component_code: 'FeedGridLoadToolPanel',
  runtime_tool_code: 'ig_query_references',
  aol: {
    object_kind: 'tool',
    object_uri: 'mindscape://ig/tool/feed_grid_card_load_limit',
    role: 'constraint',
  },
  state_schema: {
    load_limit: {
      type: 'integer',
      min: 1,
      max: 300,
    },
  },
  panel_component: {
    code: 'FeedGridLoadToolPanel',
    path: 'ui/workbench/feedGridTool/FeedGridLoadToolPanel.tsx',
    description: 'Feed load panel',
    export: 'FeedGridLoadToolPanel',
    artifact_types: [],
    playbook_codes: [],
    import_path: '@/app/capabilities/ig/components/workbench/feedGridTool/FeedGridLoadToolPanel',
    layout_hint: 'default',
  },
};

export const fullBleedTool: WorkspaceToolDefinition = {
  ...feedLoadTool,
  tool_key: 'ig:full_bleed_panel',
  id: 'full_bleed_panel',
  label: 'Full Panel',
  panel_component_code: 'FullBleedToolPanel',
  panel_component: {
    ...feedLoadTool.panel_component,
    code: 'FullBleedToolPanel',
    layout_hint: 'scrollable_full_bleed',
  },
};

export function createAolHost(
  onSelectObject: AddressableObjectHostBridge['onSelectObject'],
): AddressableObjectHostBridge {
  return {
    mode: 'idle',
    selection: null,
    currentMeetingId: null,
    requestObjectTargeting: vi.fn(),
    cancelObjectTargeting: vi.fn(),
    onSelectObject,
    clearCurrentObject: vi.fn(),
    openCurrentMeeting: vi.fn(),
  };
}

export function noopSelectObject(selection: AddressableSelectionTarget) {
  void selection;
}

export function ShortcutProfileController({
  onReady,
}: {
  onReady: (setProfile: (profile: KeyboardShortcutProfile) => void) => void;
}) {
  const { setProfile } = useKeyboardShortcuts();
  React.useEffect(() => {
    onReady(setProfile);
  }, [onReady, setProfile]);
  return null;
}
