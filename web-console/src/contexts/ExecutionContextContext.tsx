'use client';

import React, { createContext, useContext, ReactNode } from 'react';
import { ExecutionContext, createLocalExecutionContext } from '@/types/execution-context';

interface ExecutionContextContextType {
  context: ExecutionContext;
}

const ExecutionContextContext = createContext<ExecutionContextContextType | null>(null);

interface ExecutionContextProviderProps {
  children: ReactNode;
  workspaceId: string;
  actorId?: string;
  context?: ExecutionContext;
}

export function ExecutionContextProvider({
  children,
  workspaceId,
  actorId = 'local-user',
  context: providedContext
}: ExecutionContextProviderProps) {
  const context = providedContext || createLocalExecutionContext(workspaceId, actorId);

  return (
    <ExecutionContextContext.Provider value={{ context }}>
      {children}
    </ExecutionContextContext.Provider>
  );
}

export function useExecutionContext(): ExecutionContext {
  const contextValue = useContext(ExecutionContextContext);

  if (!contextValue) {
    throw new Error('useExecutionContext must be used within ExecutionContextProvider');
  }

  return contextValue.context;
}
