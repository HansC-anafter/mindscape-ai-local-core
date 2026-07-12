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
const PROFILE_SYNC_CHANNEL = 'mindscape.keyboard-shortcuts.profile.v1';
const PROFILE_SYNC_STORAGE_KEY = 'mindscape.keyboard-shortcuts.profile.updated.v1';

function currentWorkspaceId(): string | undefined {
  if (typeof window === 'undefined') {
    return undefined;
  }
  const match = /^\/workspaces\/([^/]+)(?:\/|$)/.exec(window.location.pathname);
  return match ? decodeURIComponent(match[1]) : undefined;
}

interface RuntimeKeyboardShortcutBridge {
  getSnapshot: () => KeyboardShortcutContextValue | null;
  subscribe: (listener: () => void) => () => void;
  setSnapshot: (sourceId: string, snapshot: KeyboardShortcutContextValue) => void;
  clearSnapshot: (sourceId: string) => void;
}

declare global {
  // Runtime ESM capability assets cannot consume the host React context directly.
  // This bridge exposes the host shortcut provider without adding per-key API calls.
  // eslint-disable-next-line no-var
  var MindscapeRuntimeKeyboardShortcuts: RuntimeKeyboardShortcutBridge | undefined;
}

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

interface ProfileSyncMessage {
  type: 'keyboard-shortcuts-profile-updated';
  sourceId: string;
  timestamp: number;
  profile: KeyboardShortcutProfile;
}

function isKeyboardShortcutProfile(value: unknown): value is KeyboardShortcutProfile {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const profile = value as Partial<KeyboardShortcutProfile>;
  return profile.schema_version === 1 && Array.isArray(profile.bindings);
}

function isProfileSyncMessage(value: unknown): value is ProfileSyncMessage {
  if (!value || typeof value !== 'object') {
    return false;
  }
  const message = value as Partial<ProfileSyncMessage>;
  return message.type === 'keyboard-shortcuts-profile-updated'
    && typeof message.sourceId === 'string'
    && isKeyboardShortcutProfile(message.profile);
}

function createProfileSyncSourceId(): string {
  return `shortcut-profile-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function getRuntimeKeyboardShortcutBridge(): RuntimeKeyboardShortcutBridge | null {
  if (typeof globalThis === 'undefined') {
    return null;
  }
  if (globalThis.MindscapeRuntimeKeyboardShortcuts) {
    return globalThis.MindscapeRuntimeKeyboardShortcuts;
  }

  let snapshot: KeyboardShortcutContextValue | null = null;
  let sourceId: string | null = null;
  const listeners = new Set<() => void>();
  const notify = () => {
    for (const listener of Array.from(listeners)) {
      listener();
    }
  };
  const bridge: RuntimeKeyboardShortcutBridge = {
    getSnapshot: () => snapshot,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    setSnapshot: (nextSourceId, nextSnapshot) => {
      sourceId = nextSourceId;
      snapshot = nextSnapshot;
      notify();
    },
    clearSnapshot: (nextSourceId) => {
      if (sourceId !== nextSourceId) {
        return;
      }
      sourceId = null;
      snapshot = null;
      notify();
    },
  };
  globalThis.MindscapeRuntimeKeyboardShortcuts = bridge;
  return bridge;
}

function useRuntimeKeyboardShortcutBridge(): KeyboardShortcutContextValue | null {
  const subscribe = React.useCallback((listener: () => void) => (
    getRuntimeKeyboardShortcutBridge()?.subscribe(listener) || (() => undefined)
  ), []);
  const getSnapshot = React.useCallback(() => (
    getRuntimeKeyboardShortcutBridge()?.getSnapshot() || null
  ), []);

  return React.useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

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
  const syncSourceIdRef = React.useRef(createProfileSyncSourceId());
  const syncChannelRef = React.useRef<BroadcastChannel | null>(null);
  const [commandsVersion, setCommandsVersion] = React.useState(0);
  const [profile, setProfileState] = React.useState<KeyboardShortcutProfile>(EMPTY_KEYBOARD_SHORTCUT_PROFILE);

  const applyProfile = React.useCallback((nextProfile: KeyboardShortcutProfile) => {
    profileRef.current = nextProfile;
    setProfileState(nextProfile);
  }, []);

  const publishProfile = React.useCallback((nextProfile: KeyboardShortcutProfile) => {
    if (typeof window === 'undefined') {
      return;
    }
    const message: ProfileSyncMessage = {
      type: 'keyboard-shortcuts-profile-updated',
      sourceId: syncSourceIdRef.current,
      timestamp: Date.now(),
      profile: nextProfile,
    };
    syncChannelRef.current?.postMessage(message);
    try {
      window.localStorage.setItem(PROFILE_SYNC_STORAGE_KEY, JSON.stringify(message));
    } catch {
      // Ignore storage failures; BroadcastChannel remains the primary sync path.
    }
  }, []);

  const setProfile = React.useCallback((nextProfile: KeyboardShortcutProfile) => {
    applyProfile(nextProfile);
    publishProfile(nextProfile);
  }, [applyProfile, publishProfile]);

  const reloadProfile = React.useCallback(async () => {
    const result = await loadKeyboardShortcutProfile(currentWorkspaceId());
    applyProfile(result.profile);
  }, [applyProfile]);

  React.useEffect(() => {
    if (typeof window === 'undefined') {
      return undefined;
    }
    const handleSyncMessage = (value: unknown) => {
      if (!isProfileSyncMessage(value) || value.sourceId === syncSourceIdRef.current) {
        return;
      }
      applyProfile(value.profile);
    };

    if ('BroadcastChannel' in window) {
      const channel = new BroadcastChannel(PROFILE_SYNC_CHANNEL);
      channel.onmessage = (event) => handleSyncMessage(event.data);
      syncChannelRef.current = channel;
    }

    const handleStorage = (event: StorageEvent) => {
      if (event.key !== PROFILE_SYNC_STORAGE_KEY || !event.newValue) {
        return;
      }
      try {
        handleSyncMessage(JSON.parse(event.newValue));
      } catch {
        // Ignore malformed cross-tab messages.
      }
    };
    window.addEventListener('storage', handleStorage);

    return () => {
      window.removeEventListener('storage', handleStorage);
      syncChannelRef.current?.close();
      syncChannelRef.current = null;
    };
  }, [applyProfile]);


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

  React.useEffect(() => {
    const bridge = getRuntimeKeyboardShortcutBridge();
    if (!bridge) {
      return undefined;
    }
    const sourceId = syncSourceIdRef.current;
    bridge.setSnapshot(sourceId, value);
    return () => bridge.clearSnapshot(sourceId);
  }, [value]);

  return (
    <KeyboardShortcutContext.Provider value={value}>
      {children}
    </KeyboardShortcutContext.Provider>
  );
}

export function useKeyboardShortcuts(): KeyboardShortcutContextValue {
  const context = React.useContext(KeyboardShortcutContext);
  const bridgeContext = useRuntimeKeyboardShortcutBridge();
  return context || bridgeContext || FALLBACK_SHORTCUT_CONTEXT;
}
