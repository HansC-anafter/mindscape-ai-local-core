'use client';

import React, { createContext, useContext, useState, useMemo, ReactNode } from 'react';

export interface ScrollState {
  autoScroll: boolean;
  setAutoScroll: (value: boolean) => void;
  userScrolled: boolean;
  setUserScrolled: (value: boolean) => void;
  showScrollToBottom: boolean;
  setShowScrollToBottom: (value: boolean) => void;
  isInitialLoad: boolean;
  setIsInitialLoad: (value: boolean) => void;
}

const ScrollStateContext = createContext<ScrollState | null>(null);

export function ScrollStateProvider({ children }: { children: ReactNode }) {
  const [autoScroll, setAutoScroll] = useState(true);
  const [userScrolled, setUserScrolled] = useState(false);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [isInitialLoad, setIsInitialLoad] = useState(true);

  const value = useMemo(
    () => ({
      autoScroll,
      setAutoScroll,
      userScrolled,
      setUserScrolled,
      showScrollToBottom,
      setShowScrollToBottom,
      isInitialLoad,
      setIsInitialLoad,
    }),
    [autoScroll, userScrolled, showScrollToBottom, isInitialLoad]
  );

  return <ScrollStateContext.Provider value={value}>{children}</ScrollStateContext.Provider>;
}

export function useScrollState() {
  const context = useContext(ScrollStateContext);
  if (!context) {
    throw new Error('useScrollState must be used within ScrollStateProvider');
  }
  return context;
}

