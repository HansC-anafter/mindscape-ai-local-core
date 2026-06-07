import type {
  KeyboardShortcutBindingOverride,
  KeyboardShortcutCommand,
  KeyboardShortcutProfile,
} from './shortcut-types';
import {
  eventToShortcut,
  normalizeShortcut,
  type ShortcutPlatform,
} from './shortcut-normalization';

export type ShortcutResolution =
  | { status: 'matched'; shortcut: string; command: KeyboardShortcutCommand }
  | { status: 'blocked'; shortcut?: string; reason: 'editable-target' | 'conflict' | 'no-match'; commands?: KeyboardShortcutCommand[] };

export function isEditableShortcutTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tagName = target.tagName.toLowerCase();
  return tagName === 'input'
    || tagName === 'textarea'
    || tagName === 'select'
    || target.isContentEditable;
}

function scopePriority(scope: string): number {
  if (scope.startsWith('modal')) return 400;
  if (scope.startsWith('workbench')) return 300;
  if (scope.startsWith('workspace')) return 200;
  if (scope === 'global') return 100;
  return 0;
}

function isScopeActive(scope: string, activeScopes: Set<string>): boolean {
  return scope === 'global' || activeScopes.has(scope);
}

function overrideForBinding(
  profile: KeyboardShortcutProfile,
  bindingId: string,
): KeyboardShortcutBindingOverride | undefined {
  return profile.bindings.find((binding) => binding.binding_id === bindingId);
}

export function getEffectiveShortcut(
  command: Pick<KeyboardShortcutCommand, 'bindingId' | 'defaultShortcut'>,
  profile: KeyboardShortcutProfile,
): string | undefined {
  const override = overrideForBinding(profile, command.bindingId);
  if (override?.disabled) {
    return undefined;
  }
  return override?.shortcut || command.defaultShortcut || undefined;
}

export function resolveKeyboardShortcut({
  commands,
  profile,
  activeScopes,
  event,
  platform,
}: {
  commands: KeyboardShortcutCommand[];
  profile: KeyboardShortcutProfile;
  activeScopes: Set<string>;
  event: KeyboardEvent;
  platform?: ShortcutPlatform;
}): ShortcutResolution {
  const eventShortcut = eventToShortcut(event, platform);
  if (!eventShortcut) {
    return { status: 'blocked', reason: 'no-match' };
  }

  const editableTarget = isEditableShortcutTarget(event.target);
  const matches = commands.filter((command) => {
    if (command.enabled === false || !isScopeActive(command.scope, activeScopes)) {
      return false;
    }
    if (editableTarget && !command.allowEditableTargets) {
      return false;
    }
    const shortcut = getEffectiveShortcut(command, profile);
    return normalizeShortcut(shortcut, platform)?.canonical === eventShortcut.canonical;
  });

  if (matches.length === 0) {
    return {
      status: 'blocked',
      shortcut: eventShortcut.canonical,
      reason: editableTarget ? 'editable-target' : 'no-match',
    };
  }

  const highestPriority = Math.max(...matches.map((command) => scopePriority(command.scope)));
  const priorityMatches = matches.filter((command) => scopePriority(command.scope) === highestPriority);
  if (priorityMatches.length !== 1) {
    return {
      status: 'blocked',
      shortcut: eventShortcut.canonical,
      reason: 'conflict',
      commands: priorityMatches,
    };
  }

  return {
    status: 'matched',
    shortcut: eventShortcut.canonical,
    command: priorityMatches[0],
  };
}
