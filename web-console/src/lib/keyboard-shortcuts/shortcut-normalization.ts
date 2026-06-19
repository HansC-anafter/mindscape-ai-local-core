export type ShortcutPlatform = 'mac' | 'other';

export interface NormalizedShortcut {
  canonical: string;
  display: string;
  aria: string;
  modifiers: string[];
  key: string;
}

const MODIFIER_ORDER = ['Control', 'Alt', 'Shift', 'Meta'] as const;
const MODIFIER_ALIASES: Record<string, string> = {
  ctrl: 'Control',
  control: 'Control',
  alt: 'Alt',
  option: 'Alt',
  shift: 'Shift',
  meta: 'Meta',
  cmd: 'Meta',
  command: 'Meta',
};

const KEY_ALIASES: Record<string, string> = {
  '`': 'Backquote',
  '~': 'Backquote',
  backquote: 'Backquote',
  esc: 'Escape',
  escape: 'Escape',
  grave: 'Backquote',
  return: 'Enter',
  enter: 'Enter',
  space: 'Space',
  spacebar: 'Space',
  tab: 'Tab',
  backspace: 'Backspace',
  delete: 'Delete',
  del: 'Delete',
  up: 'ArrowUp',
  down: 'ArrowDown',
  left: 'ArrowLeft',
  right: 'ArrowRight',
  tilde: 'Backquote',
};

const VALID_NAMED_KEY_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]*$/;
const VALID_PUNCTUATION_PATTERN = /^[,./;'`\[\]\\=-]$/;
const MODIFIER_KEY_NAMES = new Set(['Shift', 'Control', 'Alt', 'Meta']);

export function getShortcutPlatform(): ShortcutPlatform {
  if (typeof navigator === 'undefined') {
    return 'other';
  }
  return /Mac|iPhone|iPad|iPod/i.test(navigator.platform) ? 'mac' : 'other';
}

function normalizeModifierToken(token: string, platform: ShortcutPlatform): string | null {
  const normalized = token.trim().toLowerCase();
  if (normalized === 'mod') {
    return platform === 'mac' ? 'Meta' : 'Control';
  }
  return MODIFIER_ALIASES[normalized] || null;
}

function normalizeKeyToken(token: string): string | null {
  const raw = token.trim();
  if (!raw) {
    return null;
  }
  const aliased = KEY_ALIASES[raw.toLowerCase()];
  if (aliased) {
    return aliased;
  }
  if (raw.length === 1) {
    return /[a-z]/i.test(raw) ? raw.toUpperCase() : raw;
  }
  if (/^f([1-9]|1[0-9]|2[0-4])$/i.test(raw)) {
    return raw.toUpperCase();
  }
  if (/^arrow(up|down|left|right)$/i.test(raw)) {
    const direction = raw.slice(5).toLowerCase();
    return `Arrow${direction.charAt(0).toUpperCase()}${direction.slice(1)}`;
  }
  if (VALID_NAMED_KEY_PATTERN.test(raw) || VALID_PUNCTUATION_PATTERN.test(raw)) {
    return raw.charAt(0).toUpperCase() + raw.slice(1);
  }
  return null;
}

function formatKeyForDisplay(key: string): string {
  return key === 'Backquote' ? '~' : key;
}

function keyFromKeyboardEvent(event: KeyboardEvent): string {
  if (event.code === 'Backquote') {
    return 'Backquote';
  }
  return normalizeKeyToken(event.key === ' ' ? 'Space' : event.key) || '';
}

export function normalizeShortcut(
  shortcut: string | undefined | null,
  platform: ShortcutPlatform = getShortcutPlatform(),
): NormalizedShortcut | null {
  if (!shortcut || shortcut.trim() !== shortcut || /\s/.test(shortcut)) {
    return null;
  }
  const parts = shortcut.split('+').map((part) => part.trim()).filter(Boolean);
  if (parts.length === 0) {
    return null;
  }

  const modifiers = new Set<string>();
  for (const part of parts.slice(0, -1)) {
    const modifier = normalizeModifierToken(part, platform);
    if (!modifier || modifiers.has(modifier)) {
      return null;
    }
    modifiers.add(modifier);
  }

  const key = normalizeKeyToken(parts[parts.length - 1]);
  if (!key || MODIFIER_KEY_NAMES.has(key)) {
    return null;
  }

  if (key === 'Backquote') {
    modifiers.delete('Shift');
  }

  const orderedModifiers = MODIFIER_ORDER.filter((modifier) => modifiers.has(modifier));
  const canonicalTokens = [...orderedModifiers, key];
  const displayTokens = [...orderedModifiers, formatKeyForDisplay(key)];
  return {
    canonical: canonicalTokens.join('+'),
    display: displayTokens.join('+'),
    aria: displayTokens.join('+'),
    modifiers: orderedModifiers,
    key,
  };
}

export function eventToShortcut(
  event: KeyboardEvent,
  platform: ShortcutPlatform = getShortcutPlatform(),
): NormalizedShortcut | null {
  const key = keyFromKeyboardEvent(event);
  if (!key || MODIFIER_KEY_NAMES.has(key)) {
    return null;
  }
  const tokens = [
    event.ctrlKey ? 'Control' : '',
    event.altKey ? 'Alt' : '',
    event.shiftKey && key !== 'Backquote' ? 'Shift' : '',
    event.metaKey ? 'Meta' : '',
    key,
  ].filter(Boolean);
  return normalizeShortcut(tokens.join('+'), platform);
}

export function formatShortcutForDisplay(shortcut: string | undefined | null): string | undefined {
  return normalizeShortcut(shortcut)?.display || undefined;
}

export function shortcutToAria(shortcut: string | undefined | null): string | undefined {
  return normalizeShortcut(shortcut)?.aria || undefined;
}
