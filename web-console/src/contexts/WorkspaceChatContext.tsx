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
  threadId?: string | null;
}

export function WorkspaceChatProvider({
  children,
  workspaceId,
  apiUrl = '',
  threadId,
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
