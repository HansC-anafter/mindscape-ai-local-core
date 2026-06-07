'use client';

import React from 'react';
import type {
  KeyboardShortcutCommand,
  KeyboardShortcutContextValue,
  KeyboardShortcutProfile,
} from './shortcut-types';
import {
  EMPTY_KEYBOARD_SHORTCUT_PROFILE,
  loadKeyboardShortcutProfile,
} from './shortcut-storage';
import { resolveKeyboardShortcut, getEffectiveShortcut } from './shortcut-resolver';
import { shortcutToAria } from './shortcut-normalization';

const KeyboardShortcutContext = React.createContext<KeyboardShortcutContextValue | null>(null);
const FALLBACK_SHORTCUT_CONTEXT: KeyboardShortcutContextValue = {
  commands: [],
  profile: EMPTY_KEYBOARD_SHORTCUT_PROFILE,
  registerCommand: () => () => undefined,
  activateScope: () => () => undefined,
  reloadProfile: async () => undefined,
  setProfile: () => undefined,
  getCommandShortcut: (_bindingId, defaultShortcut) => defaultShortcut,
  getCommandAriaShortcut: (_bindingId, defaultShortcut) => shortcutToAria(defaultShortcut),
};

export function KeyboardShortcutProvider({
  children,
  loadProfileOnMount = true,
}: {
  children: React.ReactNode;
  loadProfileOnMount?: boolean;
}) {
  const commandsRef = React.useRef(new Map<string, KeyboardShortcutCommand>());
  const profileRef = React.useRef<KeyboardShortcutProfile>(EMPTY_KEYBOARD_SHORTCUT_PROFILE);
  const activeScopesRef = React.useRef(new Set<string>(['global']));
  const [commandsVersion, setCommandsVersion] = React.useState(0);
  const [profile, setProfileState] = React.useState<KeyboardShortcutProfile>(EMPTY_KEYBOARD_SHORTCUT_PROFILE);

  const setProfile = React.useCallback((nextProfile: KeyboardShortcutProfile) => {
    profileRef.current = nextProfile;
    setProfileState(nextProfile);
  }, []);

  const reloadProfile = React.useCallback(async () => {
    const result = await loadKeyboardShortcutProfile();
    setProfile(result.profile);
  }, [setProfile]);

  React.useEffect(() => {
    if (!loadProfileOnMount) {
      return;
    }
    void reloadProfile();
  }, [loadProfileOnMount, reloadProfile]);

  const registerCommand = React.useCallback((command: KeyboardShortcutCommand) => {
    commandsRef.current.set(command.bindingId, command);
    setCommandsVersion((version) => version + 1);
    return () => {
      if (commandsRef.current.get(command.bindingId) === command) {
        commandsRef.current.delete(command.bindingId);
        setCommandsVersion((version) => version + 1);
      }
    };
  }, []);

  const activateScope = React.useCallback((scope: string) => {
    activeScopesRef.current.add(scope);
    return () => {
      if (scope !== 'global') {
        activeScopesRef.current.delete(scope);
      }
    };
  }, []);

  React.useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const resolution = resolveKeyboardShortcut({
        commands: Array.from(commandsRef.current.values()),
        profile: profileRef.current,
        activeScopes: activeScopesRef.current,
        event,
      });
      if (resolution.status !== 'matched') {
        return;
      }
      if (resolution.command.preventDefault !== false) {
        event.preventDefault();
      }
      resolution.command.action?.(event);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const commands = React.useMemo(
    () => Array.from(commandsRef.current.values()).sort((left, right) => (
      left.ownerType.localeCompare(right.ownerType)
      || (left.ownerId || '').localeCompare(right.ownerId || '')
      || left.label.localeCompare(right.label)
      || left.bindingId.localeCompare(right.bindingId)
    )),
    [commandsVersion],
  );

  const getCommandShortcut = React.useCallback(
    (bindingId: string, defaultShortcut?: string) => getEffectiveShortcut(
      { bindingId, defaultShortcut },
      profileRef.current,
    ),
    [],
  );

  const getCommandAriaShortcut = React.useCallback(
    (bindingId: string, defaultShortcut?: string) => shortcutToAria(
      getEffectiveShortcut({ bindingId, defaultShortcut }, profileRef.current),
    ),
    [],
  );

  const value = React.useMemo<KeyboardShortcutContextValue>(() => ({
    commands,
    profile,
    registerCommand,
    activateScope,
    reloadProfile,
    setProfile,
    getCommandShortcut,
    getCommandAriaShortcut,
  }), [
    activateScope,
    commands,
    getCommandAriaShortcut,
    getCommandShortcut,
    profile,
    registerCommand,
    reloadProfile,
    setProfile,
  ]);

  return (
    <KeyboardShortcutContext.Provider value={value}>
      {children}
    </KeyboardShortcutContext.Provider>
  );
}

export function useKeyboardShortcuts(): KeyboardShortcutContextValue {
  const context = React.useContext(KeyboardShortcutContext);
  return context || FALLBACK_SHORTCUT_CONTEXT;
}
