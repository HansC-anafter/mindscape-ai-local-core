'use client';

import React, { createContext, useContext, useRef, useMemo, ReactNode } from 'react';

export interface WorkspaceRefsState {
  messagesScrollRef: React.RefObject<HTMLDivElement>;
  textareaRef: React.RefObject<HTMLTextAreaElement>;
  fileInputRef: React.RefObject<HTMLInputElement>;
  messagesEndRef: React.RefObject<HTMLDivElement>;
  messagesContainerRef: React.RefObject<HTMLDivElement>;
}

const WorkspaceRefsContext = createContext<WorkspaceRefsState | null>(null);

export function WorkspaceRefsProvider({ children }: { children: ReactNode }) {
  const messagesScrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);

  const value = useMemo(
    () => ({
      messagesScrollRef,
      textareaRef,
      fileInputRef,
      messagesEndRef,
      messagesContainerRef,
    }),
    []
  );

  return <WorkspaceRefsContext.Provider value={value}>{children}</WorkspaceRefsContext.Provider>;
}

export function useWorkspaceRefs() {
  const context = useContext(WorkspaceRefsContext);
  if (!context) {
    throw new Error('useWorkspaceRefs must be used within WorkspaceRefsProvider');
  }
  return context;
}

