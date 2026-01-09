'use client';

import React, { ReactNode } from 'react';
import { UIStateProvider } from './UIStateContext';
import { ScrollStateProvider } from './ScrollStateContext';
import { WorkspaceMetadataProvider } from './WorkspaceMetadataContext';
import { WorkspaceRefsProvider } from './WorkspaceRefsContext';
import { MessagesProvider } from './MessagesContext';

export interface WorkspaceChatProviderProps {
  children: ReactNode;
  workspaceId: string;
  apiUrl?: string;
  threadId?: string | null;  // 🆕 Current conversation thread ID
}

/**
 * Combined provider for all WorkspaceChat contexts.
 *
 * Provides a single entry point for wrapping components with all necessary contexts.
 * Contexts are nested in the following order (outer to inner):
 * 1. MessagesProvider - Messages and execution state
 * 2. UIStateProvider - UI state (input, streaming, etc.)
 * 3. ScrollStateProvider - Scroll state
 * 4. WorkspaceMetadataProvider - Workspace metadata
 * 5. WorkspaceRefsProvider - Refs (stable references)
 */
export function WorkspaceChatProvider({
  children,
  workspaceId,
  apiUrl = '',
  threadId,  // 🆕
}: WorkspaceChatProviderProps) {
  return (
    <MessagesProvider workspaceId={workspaceId} apiUrl={apiUrl} threadId={threadId}>
      <UIStateProvider>
        <ScrollStateProvider>
          <WorkspaceMetadataProvider>
            <WorkspaceRefsProvider>{children}</WorkspaceRefsProvider>
          </WorkspaceMetadataProvider>
        </ScrollStateProvider>
      </UIStateProvider>
    </MessagesProvider>
  );
}

