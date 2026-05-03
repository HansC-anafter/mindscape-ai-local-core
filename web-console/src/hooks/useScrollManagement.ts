'use client';

import { useCallback, useEffect, useMemo } from 'react';
import { useMessages } from '@/contexts/MessagesContext';
import { useScrollState } from '@/contexts/ScrollStateContext';
import { useWorkspaceRefs } from '@/contexts/WorkspaceRefsContext';
import { useLatest } from '@/hooks/useLatest';
import { SCROLL_DEBOUNCE_MS } from '@/constants/workspaceChatConstants';

export interface ScrollManagementOptions {
  threshold?: number;
  debounceMs?: number;
  enabled?: boolean;
}

function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): T & { cancel: () => void } {
  let timeout: NodeJS.Timeout | null = null;

  const debounced = ((...args: Parameters<T>) => {
    if (timeout) {
      clearTimeout(timeout);
    }
    timeout = setTimeout(() => {
      func(...args);
    }, wait);
  }) as T & { cancel: () => void };

  debounced.cancel = () => {
    if (timeout) {
      clearTimeout(timeout);
      timeout = null;
    }
  };

  return debounced;
}

export function useScrollManagement(options?: ScrollManagementOptions) {
  const { messages } = useMessages();
  const {
    autoScroll,
    setAutoScroll,
    userScrolled,
    setUserScrolled,
    showScrollToBottom,
    setShowScrollToBottom,
    isInitialLoad,
    setIsInitialLoad,
  } = useScrollState();
  const { messagesScrollRef } = useWorkspaceRefs();

  const latestOptions = useLatest(options);
  const threshold = latestOptions.current?.threshold ?? 150;
  const debounceMs = latestOptions.current?.debounceMs ?? SCROLL_DEBOUNCE_MS;
  const enabled = latestOptions.current?.enabled !== false;

  const scrollToBottom = useCallback(
    (force: boolean = false) => {
      if (!messagesScrollRef.current || !enabled) return;

      const jumpToBottom = () => {
        if (messagesScrollRef.current) {
          messagesScrollRef.current.scrollTop = messagesScrollRef.current.scrollHeight;
        }
      };

      if (force) {
        jumpToBottom();
        requestAnimationFrame(jumpToBottom);
        setAutoScroll(true);
        setUserScrolled(false);
      } else if (autoScroll && !userScrolled && messages.length > 0) {
        jumpToBottom();
        requestAnimationFrame(jumpToBottom);
      }
    },
    [
      messagesScrollRef,
      enabled,
      autoScroll,
      userScrolled,
      messages.length,
      setAutoScroll,
      setUserScrolled,
    ]
  );

  const handleScrollRef = useLatest(() => {
    if (!messagesScrollRef.current || !enabled) return;

    const { scrollTop, scrollHeight, clientHeight } = messagesScrollRef.current;
    const isNearBottom = scrollHeight - scrollTop - clientHeight < threshold;
    const hasContentBelow = scrollHeight > scrollTop + clientHeight + 50;

    setShowScrollToBottom(hasContentBelow && !isNearBottom);

    if (isNearBottom) {
      setUserScrolled(false);
      setAutoScroll(true);
    } else {
      setUserScrolled(true);
      setAutoScroll(false);
    }
  });

  const handleScroll = useMemo(
    () => debounce(() => handleScrollRef.current(), debounceMs),
    [debounceMs, handleScrollRef]
  );

  useEffect(() => {
    if (!enabled) return;

    const element = messagesScrollRef.current;
    if (!element) return;

    element.addEventListener('scroll', handleScroll);

    return () => {
      element.removeEventListener('scroll', handleScroll);
      handleScroll.cancel?.();
    };
  }, [messagesScrollRef, handleScroll, enabled]);

  useEffect(() => {
    if (isInitialLoad && messages.length > 0) {
      setIsInitialLoad(false);

      let frames = 0;
      const maxFrames = 30;
      const scrollLoop = () => {
        if (messagesScrollRef.current) {
          messagesScrollRef.current.scrollTop = messagesScrollRef.current.scrollHeight;
        }
        frames++;
        if (frames < maxFrames) {
          requestAnimationFrame(scrollLoop);
        }
      };
      requestAnimationFrame(scrollLoop);
    }
  }, [isInitialLoad, messages.length, setIsInitialLoad, messagesScrollRef]);

  return {
    scrollToBottom,
    showScrollToBottom,
    autoScroll,
    userScrolled,
  };
}
