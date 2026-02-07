'use client';

import { useEffect } from 'react';
import { useLatest } from '@/hooks/useLatest';

export interface KeyboardShortcutHandlers {
  onCopyAll?: () => void;
  onCopySelected?: (messageId: string) => void;
}

export interface KeyboardShortcutOptions {
  enabled?: boolean;
  target?: HTMLElement | Window;
}

/**
 * Hook for handling keyboard shortcuts.
 *
 * Supports:
 * - Cmd/Ctrl + Shift + C: Copy all messages
 * - Cmd/Ctrl + C: Copy selected message (if not in input field)
 *
 * @param handlers - Keyboard shortcut handlers
 * @param options - Optional configuration (enabled flag, target element)
 */
export function useKeyboardShortcuts(
  handlers: KeyboardShortcutHandlers,
  options?: KeyboardShortcutOptions
) {
  const latestHandlers = useLatest(handlers);
  const latestOptions = useLatest(options);

  useEffect(() => {
    if (latestOptions.current?.enabled === false) {
      return;
    }

    const target = latestOptions.current?.target || window;

    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'C') {
        e.preventDefault();
        latestHandlers.current.onCopyAll?.();
      } else if ((e.metaKey || e.ctrlKey) && e.key === 'c' && !e.shiftKey) {
        const activeElement = document.activeElement;
        if (
          activeElement &&
          (activeElement.tagName === 'TEXTAREA' ||
            activeElement.tagName === 'INPUT' ||
            (activeElement as HTMLElement).isContentEditable)
        ) {
          return;
        }

        if (latestHandlers.current.onCopySelected) {
          const selectedMessageId = getSelectedMessageId();
          if (selectedMessageId) {
            e.preventDefault();
            latestHandlers.current.onCopySelected(selectedMessageId);
          }
        }
      }
    };

    target.addEventListener('keydown', handleKeyDown as EventListener);

    return () => {
      target.removeEventListener('keydown', handleKeyDown as EventListener);
    };
  }, [latestHandlers, latestOptions, latestOptions.current?.enabled, latestOptions.current?.target]);
}

/**
 * Get the ID of the currently selected message.
 *
 * @returns Message ID if a message is selected, null otherwise
 */
function getSelectedMessageId(): string | null {
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0) {
    return null;
  }

  const range = selection.getRangeAt(0);
  let element: Element | null = range.commonAncestorContainer as Element;

  if (element.nodeType !== Node.ELEMENT_NODE) {
    element = (element as any).parentElement;
  }

  while (element && element !== document.body) {
    const messageId = element.getAttribute?.('data-message-id');
    if (messageId) {
      return messageId;
    }
    element = element.parentElement;
  }

  return null;
}

