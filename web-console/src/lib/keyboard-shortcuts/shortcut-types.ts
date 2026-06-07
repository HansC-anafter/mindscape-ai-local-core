export type KeyboardShortcutOwnerType = 'core' | 'pack';

export interface KeyboardShortcutBindingOverride {
  binding_id: string;
  command_id: string;
  owner_type: KeyboardShortcutOwnerType;
  owner_id?: string | null;
  shortcut?: string | null;
  disabled?: boolean;
}

export interface KeyboardShortcutProfile {
  schema_version: 1;
  bindings: KeyboardShortcutBindingOverride[];
}

export interface KeyboardShortcutCatalogItem {
  bindingId: string;
  commandId: string;
  label: string;
  ownerType: KeyboardShortcutOwnerType;
  ownerId?: string;
  ownerLabel?: string;
  defaultShortcut?: string;
  scope: string;
  source: string;
  metadata?: Record<string, unknown>;
}

export interface KeyboardShortcutCommand {
  bindingId: string;
  commandId: string;
  label: string;
  ownerType: KeyboardShortcutOwnerType;
  ownerId?: string;
  ownerLabel?: string;
  defaultShortcut?: string;
  scope: string;
  description?: string;
  preventDefault?: boolean;
  allowEditableTargets?: boolean;
  enabled?: boolean;
  action?: (event: KeyboardEvent) => void;
}

export interface KeyboardShortcutConflict {
  shortcut: string;
  scope: string;
  bindingIds: string[];
}

export interface KeyboardShortcutProfileResponse extends KeyboardShortcutProfile {
  updated_at?: string | null;
  catalog?: Array<{
    binding_id: string;
    command_id: string;
    label: string;
    owner_type: KeyboardShortcutOwnerType;
    owner_id?: string | null;
    owner_label?: string | null;
    default_shortcut?: string | null;
    scope: string;
    source: string;
    metadata?: Record<string, unknown>;
  }>;
}

export interface KeyboardShortcutContextValue {
  commands: KeyboardShortcutCommand[];
  profile: KeyboardShortcutProfile;
  registerCommand: (command: KeyboardShortcutCommand) => () => void;
  activateScope: (scope: string) => () => void;
  reloadProfile: () => Promise<void>;
  setProfile: (profile: KeyboardShortcutProfile) => void;
  getCommandShortcut: (bindingId: string, defaultShortcut?: string) => string | undefined;
  getCommandAriaShortcut: (bindingId: string, defaultShortcut?: string) => string | undefined;
}
