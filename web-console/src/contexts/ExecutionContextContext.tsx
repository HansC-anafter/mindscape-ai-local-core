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

/**
 * ExecutionContextProvider - Provides ExecutionContext to the component tree
 *
 * This provider makes ExecutionContext available to all child components
 * via the useExecutionContext() hook.
 *
 * In local mode, it creates a default context with mode: "local".
 * In cloud mode, the context should be provided via props (with cloud tags).
 */
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

/**
 * useExecutionContext - Hook to access ExecutionContext
 *
 * @throws Error if used outside ExecutionContextProvider
 */
export function useExecutionContext(): ExecutionContext {
  const contextValue = useContext(ExecutionContextContext);

  if (!contextValue) {
    throw new Error('useExecutionContext must be used within ExecutionContextProvider');
  }

  return contextValue.context;
}

