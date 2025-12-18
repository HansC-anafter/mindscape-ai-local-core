'use client';

import { useCallback, useEffect, RefObject } from 'react';

interface UseTextareaAutoResizeOptions {
  minHeight?: number;
  maxHeight?: number;
  lineHeight?: number;
  enabled?: boolean;
}

/**
 * useTextareaAutoResize Hook
 * Automatically adjusts textarea height based on content.
 *
 * @param textareaRef Reference to the textarea element.
 * @param value The current value of the textarea.
 * @param options Optional configuration options.
 */
export function useTextareaAutoResize(
  textareaRef: RefObject<HTMLTextAreaElement>,
  value: string,
  options?: UseTextareaAutoResizeOptions
) {
  const {
    minHeight = 40,
    maxHeight = 200,
    lineHeight = 20,
    enabled = true,
  } = options || {};

  const adjustHeight = useCallback(() => {
    if (!enabled || !textareaRef.current) {
      return;
    }

    const textarea = textareaRef.current;
    textarea.style.height = 'auto';

    const defaultHeight = lineHeight * 2;
    const scrollHeight = textarea.scrollHeight;

    if (scrollHeight <= defaultHeight) {
      textarea.style.height = `${defaultHeight}px`;
    } else {
      textarea.style.height = `${Math.min(scrollHeight, maxHeight)}px`;
    }
  }, [textareaRef, minHeight, maxHeight, lineHeight, enabled]);

  useEffect(() => {
    adjustHeight();
  }, [value, adjustHeight]);

  return {
    adjustHeight,
  };
}

