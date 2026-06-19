import { describe, expect, it } from 'vitest';

import { eventToShortcut, normalizeShortcut } from './shortcut-normalization';

describe('keyboard shortcut normalization', () => {
  it('normalizes function keys and shifted letter shortcuts', () => {
    expect(normalizeShortcut('F9')?.canonical).toBe('F9');
    expect(normalizeShortcut('Shift+S')?.canonical).toBe('Shift+S');
  });

  it('maps Mod to the platform primary modifier', () => {
    expect(normalizeShortcut('Mod+K', 'mac')?.canonical).toBe('Meta+K');
    expect(normalizeShortcut('Mod+K', 'other')?.canonical).toBe('Control+K');
  });

  it('rejects pure modifiers and sequence whitespace', () => {
    expect(normalizeShortcut('Shift')).toBeNull();
    expect(normalizeShortcut('Control+K Control+S')).toBeNull();
  });

  it('builds a shortcut from keyboard events', () => {
    const event = new KeyboardEvent('keydown', {
      key: 's',
      shiftKey: true,
    });
    expect(eventToShortcut(event)?.canonical).toBe('Shift+S');
  });

  it('normalizes the tilde key as a backquote shortcut', () => {
    expect(normalizeShortcut('~')?.canonical).toBe('Backquote');
    expect(normalizeShortcut('`')?.canonical).toBe('Backquote');
    expect(normalizeShortcut('~')?.display).toBe('~');
    expect(eventToShortcut(new KeyboardEvent('keydown', { key: '`' }))?.canonical).toBe('Backquote');
    expect(eventToShortcut(new KeyboardEvent('keydown', { key: '~', shiftKey: true }))?.canonical).toBe('Backquote');
    expect(eventToShortcut(new KeyboardEvent('keydown', { key: 'Dead', code: 'Backquote' }))?.canonical).toBe('Backquote');
  });
});
