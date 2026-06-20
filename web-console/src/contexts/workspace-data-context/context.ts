import { createContext, useContext } from 'react';
import type { WorkspaceDataContextType } from './types';

export const WorkspaceDataContext = createContext<WorkspaceDataContextType | null>(null);

export function useWorkspaceData(): WorkspaceDataContextType {
  const context = useContext(WorkspaceDataContext);
  if (!context) {
    throw new Error('useWorkspaceData must be used within a WorkspaceDataProvider');
  }
  return context;
}

export function useWorkspaceDataOptional(): WorkspaceDataContextType | null {
  return useContext(WorkspaceDataContext);
}
