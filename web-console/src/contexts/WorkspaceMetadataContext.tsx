'use client';

import React, { createContext, useContext, useState, useMemo, ReactNode } from 'react';

export interface ChatModel {
  model_name: string;
  provider: string;
}

export interface WorkspaceMetadataState {
  workspaceTitle: string;
  setWorkspaceTitle: (value: string) => void;
  systemHealth: any;
  setSystemHealth: (value: any) => void;
  contextTokenCount: number | null;
  setContextTokenCount: (value: number | null) => void;
  currentChatModel: string;
  setCurrentChatModel: (value: string) => void;
  availableChatModels: ChatModel[];
  setAvailableChatModels: (value: ChatModel[]) => void;
}

const WorkspaceMetadataContext = createContext<WorkspaceMetadataState | null>(null);

export function WorkspaceMetadataProvider({ children }: { children: ReactNode }) {
  const [workspaceTitle, setWorkspaceTitle] = useState('');
  const [systemHealth, setSystemHealth] = useState<any>(null);
  const [contextTokenCount, setContextTokenCount] = useState<number | null>(null);
  const [currentChatModel, setCurrentChatModel] = useState('');
  const [availableChatModels, setAvailableChatModels] = useState<ChatModel[]>([]);

  const value = useMemo(
    () => ({
      workspaceTitle,
      setWorkspaceTitle,
      systemHealth,
      setSystemHealth,
      contextTokenCount,
      setContextTokenCount,
      currentChatModel,
      setCurrentChatModel,
      availableChatModels,
      setAvailableChatModels,
    }),
    [workspaceTitle, systemHealth, contextTokenCount, currentChatModel, availableChatModels]
  );

  return (
    <WorkspaceMetadataContext.Provider value={value}>
      {children}
    </WorkspaceMetadataContext.Provider>
  );
}

export function useWorkspaceMetadata() {
  const context = useContext(WorkspaceMetadataContext);
  if (!context) {
    throw new Error('useWorkspaceMetadata must be used within WorkspaceMetadataProvider');
  }
  return context;
}

